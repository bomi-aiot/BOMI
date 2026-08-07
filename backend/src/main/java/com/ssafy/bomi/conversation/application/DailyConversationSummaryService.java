package com.ssafy.bomi.conversation.application;

import com.ssafy.bomi.conversation.domain.ConversationMessage;
import com.ssafy.bomi.conversation.domain.ConversationSummary;
import com.ssafy.bomi.conversation.domain.MessageRole;
import com.ssafy.bomi.conversation.domain.SummaryType;
import com.ssafy.bomi.conversation.repository.ConversationMessageRepository;
import com.ssafy.bomi.conversation.repository.ConversationSummaryRepository;
import com.ssafy.bomi.llm.application.TextGenerator;
import com.ssafy.bomi.llm.config.LlmProperties;
import com.ssafy.bomi.user.application.SeniorDayBoundary;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.domain.UserStatus;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.time.Clock;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 어르신의 전날 하루치 대화를 한 줄기 요약으로 접는다 — DAILY 요약의 유일한 생성 경로
 * (S15P11E102 G1).
 *
 * <p><b>이 클래스가 없으면 무엇이 조용히 깨지는가.</b> {@link ConversationSummary#forDay}
 * 는 정의만 있고 호출자가 0건이라, {@code conversation_summary} 에 DAILY 행이 한 번도
 * 만들어진 적이 없다. 되먹임 배관({@code ConversationContextService.selectRelevantSummaries})
 * 은 이미 완성돼 있어서 이 공백이 예외로 드러나지 않는다 — 로봇은 "며칠 전 얘기"를 대화
 * 단위로만 기억하고, 하루를 가로지르는 맥락은 아무 로그도 남기지 않은 채 그냥 없다.</p>
 *
 * <p><b>{@link ConversationSummaryService} 와 같은 3단계</b>(짧은 읽기 TX → TX 밖 LLM
 * 호출 → 짧은 쓰기 TX)를 쓴다. 이유도 같다: Hikari 기본 풀은 커넥션 10개인데 초 단위가
 * 걸리는 생성 호출이 그중 하나를 쥐고 있으면, 어르신의 턴 경로(문맥 조립, ~2초 예산)가
 * 그 뒤에 줄을 선다. 그래서 이 클래스에는 {@code @Transactional} 이 하나도 없고
 * {@link TransactionTemplate} 을 직접 들고 있다.</p>
 *
 * <p><b>왜 두 요약 파이프라인을 한 클래스로 합치지 않는가.</b> 후보 선정(대화 쪽은
 * {@code findNeedingSummary} 한 방, 이쪽은 어르신 순회 + 로컬 시각 게이트), 멱등성의
 * 근거(대화 쪽은 {@code conversation_id} 유일, 이쪽은 4-튜플 UNIQUE), 실패 재시도
 * 주기(5분 vs 1시간)가 전부 다르다. 합치면 세 가지가 한 메서드 안에서 조건 분기로
 * 뒤섞인다.</p>
 *
 * <p><b>원문 발화를 재료로 쓴다</b> — CONVERSATION 요약을 다시 요약하지 않는다. 원문이
 * 권위이고, 무엇보다 대화 요약 스윕이 아직 돌지 않은 대화(어제 밤에 닫힌 대화)를
 * 놓치지 않기 위해서다. 대신 프롬프트가 길어지므로
 * {@link LlmProperties#getMaxDailySummaryMessages()} 가 그 상한이다.</p>
 */
@Service
public class DailyConversationSummaryService {

    private static final Logger log =
        LoggerFactory.getLogger(DailyConversationSummaryService.class);

    /** {@code app_user.user_type} 은 enum 이 아직 아니다(AppUser 자바독 참고). */
    private static final String SENIOR = "SENIOR";

    private final AppUserRepository appUserRepository;
    private final ConversationMessageRepository messageRepository;
    private final ConversationSummaryRepository summaryRepository;
    private final SeniorDayBoundary dayBoundary;
    private final TextGenerator textGenerator;
    private final LlmProperties properties;
    private final TransactionTemplate transactions;
    private final Clock clock;

    public DailyConversationSummaryService(
        AppUserRepository appUserRepository,
        ConversationMessageRepository messageRepository,
        ConversationSummaryRepository summaryRepository,
        SeniorDayBoundary dayBoundary,
        TextGenerator textGenerator,
        LlmProperties properties,
        PlatformTransactionManager transactionManager,
        Clock clock
    ) {
        this.appUserRepository = appUserRepository;
        this.messageRepository = messageRepository;
        this.summaryRepository = summaryRepository;
        this.dayBoundary = dayBoundary;
        this.textGenerator = textGenerator;
        this.properties = properties;
        this.transactions = new TransactionTemplate(transactionManager);
        this.clock = clock;
    }

    /** 한 번의 시간별 틱이 한 일. 스케줄러가 로그로 남기고, 테스트가 단언할 수 있다. */
    public record DailySweepReport(int summarized, int skipped, int failed, boolean unavailable) {

        /**
         * 생성기가 꺼져 있어 저장소를 아예 건드리지 않은 틱.
         *
         * <p>이름이 {@code unavailable()} 이 아닌 이유는 문법이다 — 그 이름은 레코드
         * 컴포넌트 접근자가 이미 쓰고 있고, 정적 팩토리가 같은 이름을 쓰면 컴파일이
         * 깨진다.</p>
         */
        static DailySweepReport generationUnavailable() {
            return new DailySweepReport(0, 0, 0, true);
        }
    }

    /** 한 어르신의 하루에 대해 이번 틱이 내린 결론. */
    private enum DayOutcome {
        /** 새 DAILY 행을 썼다. LLM 을 한 번 불렀다. */
        SUMMARIZED,
        /** 이미 있거나 요약할 발화가 없다. LLM 을 부르지 않았다. */
        SKIPPED,
        /** 생성이나 저장이 실패했다. 다음 시간 틱이 재시도한다. */
        FAILED
    }

    /**
     * 스케줄러 진입점. 모든 어르신을 훑어, 로컬 시각이 요약 창 안에 들어온 사람의
     * 전날을 요약한다.
     *
     * <p>어르신 한 명의 실패가 나머지를 막지 않는다 — 한 사람의 LLM 실패로 그날 다른
     * 어르신의 하루가 통째로 사라지면, 그 사실은 대시보드에서 "그냥 조용한 하루"와
     * 구분되지 않는다.</p>
     */
    public DailySweepReport summarizeDueDays() {
        if (!textGenerator.isAvailable()) {
            log.debug("daily conversation summary sweep skipped: llm generation unavailable");
            return DailySweepReport.generationUnavailable();
        }

        int budget = Math.max(1, properties.getMaxCallsPerRun());
        int summarized = 0;
        int skipped = 0;
        int failed = 0;

        // 살아 있는 어르신만 순회한다. 이 배치는 DB 안에서 끝나지 않는다 — 하루치 발화
        // 원문을 프롬프트로 조립해 외부 생성형 LLM 으로 보낸다. 탈퇴한 어르신의 발화는
        // 보존기간(기본 30일) 동안 남으므로, 상태를 안 보면 탈퇴 후 30일 내내 그 사람의
        // 대화 원문이 매일 밖으로 나간다. 예외도 경고도 없이. 발송(G2)만 막고 생성을
        // 열어 두면 "내보내지만 않으면 괜찮다"가 되는데, 외부 API 로 나간 시점에 이미
        // 내보낸 것이다.
        for (AppUser senior
            : appUserRepository.findByUserTypeAndStatusOrderByIdAsc(SENIOR, UserStatus.ACTIVE)) {
            ZoneId zone = dayBoundary.zoneOf(senior.getId());
            ZonedDateTime localNow = clock.instant().atZone(zone);
            if (!isInsideWindow(localNow.getHour())) {
                continue;
            }

            // 상한은 "요약 성공 수"가 아니라 "청구된 호출 수"로 센다. 실패한 호출도
            // 돈은 나갔다 — 실패를 공짜로 치면 모델이 계속 실패하는 날 상한이 무의미해진다.
            if (summarized + failed >= budget) {
                log.warn("daily conversation summary sweep hit its per-run call cap ({}); "
                        + "the remaining seniors wait for the next hourly tick", budget);
                break;
            }

            LocalDate yesterday = localNow.toLocalDate().minusDays(1);
            switch (summarizeDay(senior.getId(), yesterday, zone)) {
                case SUMMARIZED -> summarized++;
                case SKIPPED -> skipped++;
                case FAILED -> failed++;
            }
        }

        if (summarized + failed > 0) {
            log.info("daily conversation summary sweep: {} summarized, {} skipped, {} failed "
                    + "({} billed calls, cap {})",
                summarized, skipped, failed, summarized + failed, budget);
        }
        return new DailySweepReport(summarized, skipped, failed, false);
    }

    /**
     * 한 어르신의 한 로컬 날짜를 요약한다. 몇 번을 불러도 행은 하나다.
     *
     * <p>수동 재실행·테스트의 진입점이기도 하다. 스윕을 통째로 돌리지 않고 "8월 1일만
     * 다시"를 할 수 있어야 한다.</p>
     *
     * @return 새 요약을 실제로 저장했으면 {@code true}
     */
    public boolean summarizeDay(UUID seniorId, LocalDate localDay) {
        DayOutcome outcome = summarizeDay(seniorId, localDay, dayBoundary.zoneOf(seniorId));
        return outcome == DayOutcome.SUMMARIZED;
    }

    private DayOutcome summarizeDay(UUID seniorId, LocalDate localDay, ZoneId zone) {
        SeniorDayBoundary.LocalDayWindow window = dayBoundary.windowFor(zone, localDay);

        PreparedDay prepared = transactions.execute(status -> prepare(seniorId, window));
        if (prepared == null) {
            return DayOutcome.SKIPPED;
        }

        String content;
        try {
            content = textGenerator.generate(buildPrompt(prepared));
        } catch (RuntimeException error) {
            log.warn("daily summary generation failed; nothing is written and the next hourly "
                    + "tick retries: seniorId={}, day={}", seniorId, localDay, error);
            return DayOutcome.FAILED;
        }

        try {
            Boolean saved = transactions.execute(status -> saveDaily(prepared, content));
            return Boolean.TRUE.equals(saved) ? DayOutcome.SUMMARIZED : DayOutcome.FAILED;
        } catch (DataIntegrityViolationException duplicate) {
            // UNIQUE 가 최종 방어선으로 작동했다 — 선검사와 INSERT 사이에 다른 인스턴스가
            // 같은 날을 썼다는 뜻이다.
            //
            // 이 catch 는 반드시 transactions.execute(...) **밖**에 있어야 한다. 콜백
            // 안에서 잡으면 이미 rollback-only 로 표시된 트랜잭션이 커밋 시점에
            // UnexpectedRollbackException 으로 다시 터지고, 그 예외는 스윕 전체를 죽인다.
            log.debug("daily summary already exists (concurrent tick?): seniorId={}, day={}",
                seniorId, localDay);
            return DayOutcome.FAILED;
        }
    }

    /** 로컬 시각이 요약 창 {@code [hour, hour + windowHours)} 안인가. */
    private boolean isInsideWindow(int localHour) {
        int start = Math.max(0, Math.min(23, properties.getDailySummaryHour()));
        // 창이 자정을 넘으면 창의 앞뒤에서 "어제"가 서로 다른 날짜를 가리켜 하루가 두
        // 번 요약된다. 그래서 24 에서 자른다 — 설정을 고쳐 주는 게 아니라, 잘못된
        // 설정이 이중 요약으로 번지지 않게 막는 것이다.
        int end = Math.min(24, start + Math.max(1, properties.getDailySummaryWindowHours()));
        return localHour >= start && localHour < end;
    }

    /**
     * 요약에 필요한 원자료를 짧은 읽기 트랜잭션 안에서 한 번에 읽는다.
     *
     * <p><b>순서가 중요하다 — 존재 검사가 먼저다.</b> 이미 요약이 있는 날에 발화부터
     * 읽으면 그 뒤에 프롬프트를 조립하고 싶어지고, 결국 창의 매시간 재시도가 전부
     * 과금된다.</p>
     *
     * @return 요약을 만들 재료. 이미 요약이 있거나 요약할 발화가 없으면 {@code null}
     */
    private PreparedDay prepare(UUID seniorId, SeniorDayBoundary.LocalDayWindow window) {
        if (summaryRepository.existsBySeniorIdAndSummaryTypeAndPeriodStartedAtAndPeriodEndedAt(
            seniorId, SummaryType.DAILY, window.from(), window.to())) {
            return null;
        }

        List<ConversationMessage> newestFirst = messageRepository.findUnsealedForSeniorBetween(
            seniorId, window.from(), window.to(),
            PageRequest.of(0, Math.max(1, properties.getMaxDailySummaryMessages())));
        if (newestFirst.isEmpty()) {
            // 발화가 0건인 날은 행을 만들지 않는다. "어제 대화가 없었습니다" 같은 요약을
            // 저장하면 두 가지가 깨진다. (1) selectRelevantSummaries 가 그걸 "지난
            // 대화"로 로봇에게 먹여서, 로봇이 있지도 않은 침묵을 화제로 꺼낸다.
            // (2) 로봇이 꺼져 있어서 보고를 못 한 날과 어르신이 조용했던 날을 구분할 수
            // 없게 된다 — 모르는 것과 0은 다르다(CLAUDE.md §9,
            // DailyActivityMetricService.applyConversationMetrics 가 같은 이유로 컬럼을
            // 건드리지 않고 INFO 만 남긴다).
            log.debug("no unsealed utterances for {} on {}; writing no daily summary",
                seniorId, window.day());
            return null;
        }

        // Java 17 툴체인이다 — List.reversed() 는 21 부터라 직접 뒤집는다
        // (ConversationSummaryService.prepare 와 같은 이유).
        List<ConversationMessage> chronological = new ArrayList<>(newestFirst.size());
        for (int index = newestFirst.size() - 1; index >= 0; index--) {
            chronological.add(newestFirst.get(index));
        }
        return new PreparedDay(seniorId, window.day(), window.from(), window.to(), chronological);
    }

    /**
     * 하루 요약을 저장한다.
     *
     * <p>{@code saveAndFlush} 인 이유 — UNIQUE 위반이 이 콜백 <em>안</em>에서 터져야
     * 바깥의 {@code DataIntegrityViolationException} catch 가 그것을 확실히 잡는다.
     * 커밋 시점까지 미루면 예외가 트랜잭션 경계 밖의 다른 모양으로 새어 나올 수 있다.</p>
     *
     * <p>어르신의 {@code time_zone} 이 나중에 바뀌면 같은 달력 날짜의
     * {@code (period_started_at, period_ended_at)} 이 다른 instant 가 되어 UNIQUE 를
     * 통과하고 두 번째 DAILY 행이 생긴다. 기간이 실제로 다르므로 논리적으로는 옳지만
     * 대시보드에는 하루가 두 번 보인다. {@code superseded_by_id} 로 이어 붙이는 처리는
     * 이번 범위 밖이다.</p>
     */
    private boolean saveDaily(PreparedDay prepared, String content) {
        ConversationSummary summary = ConversationSummary.forDay(
            prepared.seniorId(), prepared.periodStart(), prepared.periodEnd(),
            content, prepared.messages().size());
        summaryRepository.saveAndFlush(summary);
        return true;
    }

    /**
     * 하루 요약 프롬프트를 조립한다.
     *
     * <p>Prompts are code — 목적: 하루에 흩어져 있던 여러 대화를 로봇이 다음에 만났을 때
     * 참고할 한 줄기로 접는다. 어느 저장소가 먹는가: 결과가
     * {@code conversation_summary.content}(summary_type=DAILY) 로 저장되고, 로봇 쪽
     * {@code prompts/builder.py} 의 "지난 대화" 섹션이 CONVERSATION 요약과 나란히
     * 읽는다. 예상 출력 모양: 존댓말 평서문 3~5문장, 목록·번호 없음.</p>
     *
     * <p>화자 라벨과 규칙 3줄을 {@code ConversationSummaryService.buildPrompt} 와 글자
     * 단위로 맞춘 것은 취향이 아니다 — 두 요약이 같은 "지난 대화" 섹션에 나란히
     * 렌더링되므로, 어조가 갈리면 로봇의 말투가 문장 단위로 튄다.</p>
     */
    private String buildPrompt(PreparedDay prepared) {
        StringBuilder transcript = new StringBuilder();
        for (ConversationMessage message : prepared.messages()) {
            String speaker = message.getRole() == MessageRole.SENIOR ? "어르신" : "로봇";
            transcript.append(speaker).append(": ").append(message.getContent()).append('\n');
        }
        return """
            다음은 %s 하루 동안 돌봄 로봇과 어르신이 나눈 대화입니다. 여러 번의 대화가 \
            섞여 있을 수 있습니다. 이 하루를 로봇이 다음에 만났을 때 참고할 수 있도록 \
            세 문장에서 다섯 문장으로 요약하세요.
            - 대화에 실제로 있었던 내용만 쓰고, 없는 내용을 지어내지 마세요.
            - 진단이나 의학적 판단을 내리지 마세요.
            - 존댓말 평서문으로, 목록이나 번호 없이 문장으로만 쓰세요.

            대화:
            %s
            """.formatted(prepared.day(), transcript.toString().strip());
    }

    /** 프롬프트 조립과 저장에 필요한, 한 번의 읽기 트랜잭션에서 모은 값들. */
    private record PreparedDay(
        UUID seniorId,
        LocalDate day,
        OffsetDateTime periodStart,
        OffsetDateTime periodEnd,
        List<ConversationMessage> messages) {
    }
}
