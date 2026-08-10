package com.ssafy.bomi.conversation.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.ssafy.bomi.conversation.application.DailyConversationSummaryService.DailySweepReport;
import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationMessage;
import com.ssafy.bomi.conversation.domain.ConversationStatus;
import com.ssafy.bomi.conversation.domain.ConversationSummary;
import com.ssafy.bomi.conversation.domain.MessageRole;
import com.ssafy.bomi.conversation.domain.SummaryType;
import com.ssafy.bomi.conversation.repository.ConversationMessageRepository;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import com.ssafy.bomi.conversation.repository.ConversationSummaryRepository;
import com.ssafy.bomi.llm.application.TextGenerator;
import com.ssafy.bomi.llm.config.LlmProperties;
import com.ssafy.bomi.user.application.SeniorDayBoundary;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.domain.UserStatus;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;

/**
 * {@code DailyConversationSummaryService} 의 완료 조건을 검증한다 (S15P11E102 G1).
 *
 * <p>{@code ConversationSummaryServiceTest} 와 같은 모양이다 — 실제 JPA 저장소(H2,
 * datajpa 프로파일)와 결정적 가짜 {@code TextGenerator}. 여기서 확인하는 것은 전부
 * "부기"(누구의 어느 하루가 뽑히는가, 몇 번 불렸는가, 무엇이 프롬프트에 들어가는가)
 * 이지 모델이 실제로 무슨 문장을 쓰는지가 아니다.</p>
 *
 * <p>시계를 {@code 2026-08-06T17:20Z} 로 고정한다. 이 한 순간이 서울에서는
 * <b>08-07 새벽 02:20</b>(요약 창 안)이고 뉴욕에서는 <b>08-06 오후 13:20</b>(창 밖)이다
 * — "시간대가 하나라고 가정하지 않는다"를 이 하나의 시각으로 가른다.</p>
 */
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@ActiveProfiles("datajpa")
class DailyConversationSummaryServiceTest {

    /** 서울 02:20 = 뉴욕 13:20. 창은 로컬 [02:00, 06:00). */
    private static final Instant INSIDE_SEOUL_WINDOW = Instant.parse("2026-08-06T17:20:00Z");

    /** 서울 09:20 — 창 한참 밖. */
    private static final Instant OUTSIDE_SEOUL_WINDOW = Instant.parse("2026-08-07T00:20:00Z");

    /** 서울 기준 "어제"(= 2026-08-06)의 반열린 구간. */
    private static final LocalDate SEOUL_YESTERDAY = LocalDate.of(2026, 8, 6);
    private static final OffsetDateTime SEOUL_DAY_FROM =
        OffsetDateTime.parse("2026-08-06T00:00:00+09:00");
    private static final OffsetDateTime SEOUL_DAY_TO =
        OffsetDateTime.parse("2026-08-07T00:00:00+09:00");

    @Autowired AppUserRepository appUserRepository;
    @Autowired ConversationRepository conversationRepository;
    @Autowired ConversationMessageRepository messageRepository;
    @Autowired ConversationSummaryRepository summaryRepository;
    @Autowired PlatformTransactionManager transactionManager;
    @Autowired TestEntityManager em;

    private FakeTextGenerator textGenerator;
    private LlmProperties properties;
    private SeniorDayBoundary dayBoundary;

    @BeforeEach
    void setUp() {
        textGenerator = new FakeTextGenerator();
        properties = new LlmProperties();
        properties.setMaxCallsPerRun(20);
        properties.setMaxDailySummaryMessages(200);
        properties.setDailySummaryHour(2);
        properties.setDailySummaryWindowHours(4);
        dayBoundary = new SeniorDayBoundary(appUserRepository);
    }

    // ── 기본값이 꺼짐 ────────────────────────────────────────────────────────

    @Test
    @DisplayName("★ LLM 이 꺼져 있으면 저장소를 건드리지 않고 조용히 넘어간다")
    void skipsEntirelyWhenGenerationIsUnavailable() {
        UUID seniorId = senior("Asia/Seoul");
        conversation(seniorId, false, "어제 무릎이 좀 쑤셨어요", yesterdayAt(10));
        textGenerator.available = false;

        DailySweepReport report = serviceAt(INSIDE_SEOUL_WINDOW).summarizeDueDays();

        assertThat(report.unavailable()).isTrue();
        assertThat(report.summarized()).isZero();
        assertThat(textGenerator.calls).isZero();
        assertThat(summaryRepository.count()).isZero();
    }

    // ── 무엇을, 어느 기간으로 요약하는가 ─────────────────────────────────────

    @Test
    @DisplayName("전날 발화가 있는 어르신에게 DAILY 요약이 정확히 하나 생긴다")
    void writesOneDailySummaryForYesterday() {
        UUID seniorId = senior("Asia/Seoul");
        conversation(seniorId, false, "어제 무릎이 좀 쑤셨어요", yesterdayAt(10), yesterdayAt(11));

        DailySweepReport report = serviceAt(INSIDE_SEOUL_WINDOW).summarizeDueDays();
        em.flush();
        em.clear();

        assertThat(report.summarized()).isEqualTo(1);
        assertThat(report.failed()).isZero();
        List<ConversationSummary> saved = summaryRepository.findAll();
        assertThat(saved).hasSize(1);
        ConversationSummary daily = saved.get(0);
        assertThat(daily.getSummaryType()).isEqualTo(SummaryType.DAILY);
        assertThat(daily.getConversationId())
            .as("DAILY 는 대화 하나에 매이지 않는다 — 하루가 단위다")
            .isNull();
        assertThat(daily.getPeriodStartedAt().toInstant()).isEqualTo(SEOUL_DAY_FROM.toInstant());
        assertThat(daily.getPeriodEndedAt().toInstant()).isEqualTo(SEOUL_DAY_TO.toInstant());
        assertThat(daily.getSourceMessageCount()).isEqualTo(2);
        assertThat(daily.getContent()).isNotBlank();
        assertThat(textGenerator.lastPrompt)
            .as("프롬프트에는 그날의 원문이 시간순으로 들어간다")
            .contains(SEOUL_YESTERDAY.toString())
            .contains("어제 무릎이 좀 쑤셨어요 0")
            .contains("어제 무릎이 좀 쑤셨어요 1");
    }

    @Test
    @DisplayName("전날 발화가 하나도 없으면 행을 만들지 않는다 — 모르는 것과 0은 다르다")
    void writesNothingWhenTheDayHadNoUtterances() {
        senior("Asia/Seoul");

        DailySweepReport report = serviceAt(INSIDE_SEOUL_WINDOW).summarizeDueDays();

        assertThat(report.summarized()).isZero();
        assertThat(report.skipped()).isEqualTo(1);
        assertThat(textGenerator.calls).isZero();
        assertThat(summaryRepository.count()).isZero();
    }

    @Test
    @DisplayName("반열린 구간 — 전날 23:59:59 는 들어가고 당일 00:00:00 은 빠진다")
    void theDayWindowIsHalfOpen() {
        UUID seniorId = senior("Asia/Seoul");
        conversation(seniorId, false, "자정 언저리",
            OffsetDateTime.parse("2026-08-06T23:59:59+09:00"),
            OffsetDateTime.parse("2026-08-07T00:00:00+09:00"));

        serviceAt(INSIDE_SEOUL_WINDOW).summarizeDueDays();
        em.flush();
        em.clear();

        ConversationSummary daily = summaryRepository.findAll().get(0);
        assertThat(daily.getSourceMessageCount())
            .as("자정 발화가 이틀에 두 번 세어지면 안 된다")
            .isEqualTo(1);
        assertThat(textGenerator.lastPrompt).contains("자정 언저리 0").doesNotContain("자정 언저리 1");
    }

    // ── 시간대 ───────────────────────────────────────────────────────────────

    @Test
    @DisplayName("★ 로컬 시각이 창 안인 어르신만 요약된다 — UTC 고정 cron 회귀 방지")
    void onlyTheSeniorWhoseLocalClockIsInsideTheWindowIsSummarized() {
        UUID seoul = senior("Asia/Seoul");
        UUID newYork = senior("America/New_York");
        conversation(seoul, false, "서울 어르신 이야기", yesterdayAt(10));
        // 뉴욕 어르신에게도 자기 기준 어제 발화를 준다 — 재료가 없어서 건너뛴 것이
        // 아니라 "지금 그 사람 시각이 낮 1시라서" 건너뛴 것임을 분명히 한다.
        conversation(newYork, false, "뉴욕 어르신 이야기",
            OffsetDateTime.parse("2026-08-05T10:00:00-04:00"));

        DailySweepReport report = serviceAt(INSIDE_SEOUL_WINDOW).summarizeDueDays();
        em.flush();
        em.clear();

        assertThat(report.summarized()).isEqualTo(1);
        assertThat(textGenerator.calls).isEqualTo(1);
        assertThat(summaryRepository.findAll())
            .singleElement()
            .extracting(ConversationSummary::getSeniorId)
            .isEqualTo(seoul);
        assertThat(newYork).isNotEqualTo(seoul);
    }

    @Test
    @DisplayName("로컬 시각이 창 밖이면 아무 것도 하지 않는다")
    void doesNothingOutsideTheWindow() {
        UUID seniorId = senior("Asia/Seoul");
        conversation(seniorId, false, "어제 이야기", yesterdayAt(10));

        DailySweepReport report = serviceAt(OUTSIDE_SEOUL_WINDOW).summarizeDueDays();

        assertThat(report.summarized()).isZero();
        assertThat(textGenerator.calls).isZero();
        assertThat(summaryRepository.count()).isZero();
    }

    // ── 봉인 ─────────────────────────────────────────────────────────────────

    @Test
    @DisplayName("★ 봉인된 대화뿐인 날은 요약 자체가 만들어지지 않는다 (CLAUDE.md §9 T4)")
    void aDayOfOnlySealedConversationsIsNeverSummarized() {
        UUID seniorId = senior("Asia/Seoul");
        conversation(seniorId, true, "우리끼리 얘기", yesterdayAt(10));

        DailySweepReport report = serviceAt(INSIDE_SEOUL_WINDOW).summarizeDueDays();

        assertThat(report.summarized()).isZero();
        assertThat(textGenerator.calls)
            .as("봉인된 원문은 프롬프트로 조립되어서도 안 된다")
            .isZero();
        assertThat(summaryRepository.count()).isZero();
    }

    @Test
    @DisplayName("★ 봉인·비봉인이 섞인 날이면 요약은 생기되 봉인 내용은 프롬프트에 없다")
    void sealedUtterancesNeverReachThePromptOnAMixedDay() {
        UUID seniorId = senior("Asia/Seoul");
        conversation(seniorId, true, "봉인된비밀", yesterdayAt(9));
        conversation(seniorId, false, "평범한이야기", yesterdayAt(10), yesterdayAt(11));

        DailySweepReport report = serviceAt(INSIDE_SEOUL_WINDOW).summarizeDueDays();
        em.flush();
        em.clear();

        assertThat(report.summarized()).isEqualTo(1);
        assertThat(textGenerator.lastPrompt)
            .as("한 줄이라도 새면 그 내용이 요약문에 영구 저장되고 로봇 입으로 되돌아온다")
            .doesNotContain("봉인된비밀")
            .contains("평범한이야기");
        assertThat(summaryRepository.findAll().get(0).getSourceMessageCount())
            .as("발화 수도 비봉인 발화만 센다")
            .isEqualTo(2);
    }

    @Test
    @DisplayName("★ 아직 열려 있는 대화의 발화는 프롬프트에 실리지 않는다 — 봉인될 기회가 없었다")
    void anOpenConversationNeverReachesThePrompt() {
        UUID seniorId = senior("Asia/Seoul");
        // 로봇이 POST /end(sealed=true) 를 보내지 못한 채 자정을 넘긴 대화.
        // 아웃박스 재시도 설계상 정상적으로 일어나는 상태다(네트워크 단절).
        conversation(seniorId, false, false, "아직닫히지않은말", yesterdayAt(23));

        DailySweepReport report = serviceAt(INSIDE_SEOUL_WINDOW).summarizeDueDays();

        assertThat(textGenerator.calls)
            .as("sealed=false 는 '봉인되지 않았다'가 아니라 '아직 봉인될 기회가 없었다'일 수 "
                + "있다. 아침에 sealed=true 로 재전송돼도 이미 외부 LLM 으로 나간 뒤다")
            .isZero();
        assertThat(report.summarized()).isZero();
        assertThat(summaryRepository.count()).isZero();
    }

    @Test
    @DisplayName("★ 탈퇴한 어르신의 발화는 외부 LLM 으로 나가지 않는다")
    void aWithdrawnSeniorIsNeverSummarised() {
        UUID seniorId = senior("Asia/Seoul");
        conversation(seniorId, false, "평범한이야기", yesterdayAt(10));
        AppUser withdrawn = appUserRepository.findById(seniorId).orElseThrow();
        withdrawn.changeStatus(UserStatus.WITHDRAWN);
        appUserRepository.saveAndFlush(withdrawn);

        DailySweepReport report = serviceAt(INSIDE_SEOUL_WINDOW).summarizeDueDays();

        assertThat(textGenerator.calls)
            .as("발화는 보존기간(기본 30일) 동안 남는다. 상태를 안 보면 탈퇴 후 30일 내내 "
                + "그 사람의 대화 원문이 매일 외부 API 로 나간다 — 예외도 경고도 없이")
            .isZero();
        assertThat(report.summarized()).isZero();
    }

    // ── 멱등 ─────────────────────────────────────────────────────────────────

    @Test
    @DisplayName("★ 같은 스윕을 두 번 돌려도 DAILY 요약이 중복 생성되지 않고 LLM 도 한 번만 불린다")
    void runningTheSweepTwiceDoesNotDuplicateTheDay() {
        UUID seniorId = senior("Asia/Seoul");
        conversation(seniorId, false, "어제 이야기", yesterdayAt(10));
        DailyConversationSummaryService service = serviceAt(INSIDE_SEOUL_WINDOW);

        DailySweepReport first = service.summarizeDueDays();
        DailySweepReport second = service.summarizeDueDays();
        em.flush();
        em.clear();

        assertThat(first.summarized()).isEqualTo(1);
        assertThat(second.summarized())
            .as("존재 선검사가 LLM 호출 자체를 막는다 — 창의 매시간 재시도가 과금되면 안 된다")
            .isZero();
        assertThat(second.skipped()).isEqualTo(1);
        assertThat(textGenerator.calls).isEqualTo(1);
        assertThat(summaryRepository.count()).isEqualTo(1);
    }

    @Test
    @DisplayName("★ UNIQUE 제약이 최종 방어선으로 실재한다 — 같은 4-튜플 두 번째 행은 거부된다")
    void theUniqueConstraintRejectsASecondRowForTheSameDay() {
        UUID seniorId = senior("Asia/Seoul");
        summaryRepository.saveAndFlush(ConversationSummary.forDay(
            seniorId, SEOUL_DAY_FROM, SEOUL_DAY_TO, "첫 번째 요약", 3));

        assertThatThrownBy(() -> summaryRepository.saveAndFlush(ConversationSummary.forDay(
            seniorId, SEOUL_DAY_FROM, SEOUL_DAY_TO, "두 번째 요약", 3)))
            .isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    @DisplayName("★ 저장 시점의 중복 예외가 스윕을 죽이지 않고 failed 로 집계된다")
    void aDuplicateAtSaveTimeIsCaughtAndCountedAsFailed() {
        UUID seniorId = senior("Asia/Seoul");
        conversation(seniorId, false, "어제 이야기", yesterdayAt(10));
        // 선검사를 통과한 뒤 INSERT 만 터지는 상황(다른 인스턴스가 그 사이에 썼다)을
        // 재현한다. 진짜 제약 위반은 위 테스트가 따로 확인하고, 여기서는 "그 예외가
        // execute() 밖에서 잡혀 스윕이 계속되는가"만 본다 — 이 catch 가 콜백 안에
        // 있으면 UnexpectedRollbackException 이 스윕 전체를 죽인다.
        DailyConversationSummaryService service = service(
            INSIDE_SEOUL_WINDOW, failingOnSave(summaryRepository));

        DailySweepReport report = service.summarizeDueDays();

        assertThat(report.failed()).isEqualTo(1);
        assertThat(report.summarized()).isZero();
        assertThat(textGenerator.calls).isEqualTo(1);
    }

    // ── 지출 상한과 실패 격리 ────────────────────────────────────────────────

    @Test
    @DisplayName("★ 한 틱의 생성 호출 수가 실행당 상한을 넘지 않는다 — 이것은 지출 상한이다")
    void oneTickNeverExceedsMaxCallsPerRun() {
        properties.setMaxCallsPerRun(1);
        for (int i = 0; i < 3; i++) {
            UUID seniorId = senior("Asia/Seoul");
            conversation(seniorId, false, "어르신 " + i + " 이야기", yesterdayAt(10));
        }

        DailySweepReport report = serviceAt(INSIDE_SEOUL_WINDOW).summarizeDueDays();
        em.flush();
        em.clear();

        assertThat(textGenerator.calls).isEqualTo(1);
        assertThat(report.summarized()).isEqualTo(1);
        assertThat(summaryRepository.count())
            .as("나머지 어르신은 다음 시간 틱으로 넘어간다 — 창이 넓은 이유가 이것이다")
            .isEqualTo(1);
    }

    @Test
    @DisplayName("★ 한 어르신의 LLM 실패가 나머지 어르신을 막지 않는다")
    void oneSeniorsFailureDoesNotBlockTheOthers() {
        UUID willFail = senior("Asia/Seoul");
        UUID willSucceed = senior("Asia/Seoul");
        conversation(willFail, false, "실패할하루", yesterdayAt(10));
        conversation(willSucceed, false, "성공할하루", yesterdayAt(10));
        textGenerator.explodeWhenPromptContains = "실패할하루";

        DailySweepReport report = serviceAt(INSIDE_SEOUL_WINDOW).summarizeDueDays();
        em.flush();
        em.clear();

        assertThat(report.failed()).isEqualTo(1);
        assertThat(report.summarized()).isEqualTo(1);
        assertThat(summaryRepository.findAll())
            .singleElement()
            .extracting(ConversationSummary::getSeniorId)
            .isEqualTo(willSucceed);
        assertThat(conversationRepository.findAll())
            .as("요약 실패가 대화 자체를 건드리면 안 된다")
            .allSatisfy(conversation -> assertThat(conversation.isSealed()).isFalse());
    }

    // ── 수동 진입점 ──────────────────────────────────────────────────────────

    @Test
    @DisplayName("summarizeDay 는 창과 무관하게 특정 날짜 하나를 다시 요약할 수 있다")
    void summarizeDayIsAManualEntryPoint() {
        UUID seniorId = senior("Asia/Seoul");
        conversation(seniorId, false, "어제 이야기", yesterdayAt(10));

        // 창 밖 시각으로 만든 서비스여도 직접 호출은 통과한다 — 창 판정은 스윕의 몫이다.
        boolean written = serviceAt(OUTSIDE_SEOUL_WINDOW).summarizeDay(seniorId, SEOUL_YESTERDAY);
        em.flush();

        assertThat(written).isTrue();
        assertThat(summaryRepository.count()).isEqualTo(1);
    }

    // ── 도우미 ───────────────────────────────────────────────────────────────

    private DailyConversationSummaryService serviceAt(Instant now) {
        return service(now, summaryRepository);
    }

    private DailyConversationSummaryService service(
        Instant now, ConversationSummaryRepository summaries) {
        return new DailyConversationSummaryService(appUserRepository, messageRepository,
            summaries, dayBoundary, textGenerator, properties, transactionManager,
            Clock.fixed(now, ZoneOffset.UTC));
    }

    private UUID senior(String timeZone) {
        AppUser user = AppUser.create("SENIOR", "김순자");
        user.changeTimeZone(timeZone);
        return appUserRepository.saveAndFlush(user).getId();
    }

    /** 서울 기준 어제({@code 2026-08-06})의 지정 시각. */
    private static OffsetDateTime yesterdayAt(int hour) {
        return SEOUL_DAY_FROM.plusHours(hour);
    }

    private void conversation(
        UUID seniorId, boolean sealed, String contentPrefix, OffsetDateTime... occurredAt) {
        conversation(seniorId, sealed, true, contentPrefix, occurredAt);
    }

    /**
     * 어제 대화 하나를 만든다.
     *
     * <p><b>왜 기본이 "닫힌" 대화인가.</b> 봉인은 종료 시점에만 세워지므로
     * ({@code Conversation.markSealed} 의 유일한 호출자가 종료 경로다) 열린 대화의
     * {@code sealed = false} 는 "봉인되지 않았다"가 아니라 "아직 봉인될 기회가
     * 없었다"이다. 그래서 요약 쿼리가 열린 대화를 통째로 뺀다. 어제 대화가 오늘
     * 새벽까지 열려 있는 것은 현실에서도 예외 상황이고(유휴 스윕이 30분이면 닫는다),
     * 픽스처가 그 예외를 기본값으로 두면 정상 경로가 한 번도 검증되지 않는다.</p>
     */
    private void conversation(UUID seniorId, boolean sealed, boolean closed,
        String contentPrefix, OffsetDateTime... occurredAt) {
        Conversation conversation = conversationRepository.save(Conversation.open(seniorId));
        for (int i = 0; i < occurredAt.length; i++) {
            messageRepository.save(ConversationMessage.reactive(
                conversation.getId(), i, MessageRole.SENIOR, contentPrefix + " " + i,
                occurredAt[i]));
        }
        if (sealed) {
            conversation.markSealed();
        }
        if (closed) {
            conversation.end(ConversationStatus.COMPLETED);
        }
        conversationRepository.save(conversation);
        em.flush();
    }

    /**
     * 존재 선검사는 진짜 저장소에 위임하되 저장만 중복 예외로 터지는 저장소.
     *
     * <p>진짜 제약 위반으로 재현하면 Hibernate 세션이 그 자리에서 못 쓰게 되어, 정작
     * 확인하고 싶은 "스윕이 계속 도는가"를 볼 수 없다. 그래서 예외 <em>모양</em>만
     * 같게 만든다.</p>
     */
    private static ConversationSummaryRepository failingOnSave(
        ConversationSummaryRepository real) {
        return (ConversationSummaryRepository) Proxy.newProxyInstance(
            ConversationSummaryRepository.class.getClassLoader(),
            new Class<?>[]{ConversationSummaryRepository.class},
            (proxy, method, args) -> {
                if (method.getName().startsWith("save")) {
                    throw new DataIntegrityViolationException(
                        "uq_conversation_summary_period");
                }
                try {
                    return method.invoke(real, args);
                } catch (InvocationTargetException error) {
                    throw error.getCause();
                }
            });
    }

    /** 네트워크를 절대 타지 않는, 결정적인 가짜 생성기. */
    private static class FakeTextGenerator implements TextGenerator {
        boolean available = true;
        int calls = 0;
        String lastPrompt = null;
        String explodeWhenPromptContains = null;

        @Override
        public String generate(String prompt) {
            calls++;
            lastPrompt = prompt;
            if (explodeWhenPromptContains != null && prompt.contains(explodeWhenPromptContains)) {
                throw new GenerationFailedException("model refused this day");
            }
            return "요약: " + prompt.length() + "자 분량의 하루입니다.";
        }

        @Override
        public boolean isAvailable() {
            return available;
        }
    }
}
