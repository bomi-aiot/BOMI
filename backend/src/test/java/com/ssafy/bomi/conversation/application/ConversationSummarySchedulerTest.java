package com.ssafy.bomi.conversation.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.llm.config.LlmProperties;
import java.time.Duration;
import java.time.LocalDateTime;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.support.CronExpression;

/**
 * 일간 요약 틱의 cron 을 고정한다 (S15P11E102 G1).
 *
 * <p><b>왜 이런 테스트가 필요한가.</b> {@code ConversationSummaryScheduler} 빈은
 * {@code bomi.llm.enabled=true} 일 때만 존재하고, 이 저장소의 어떤 테스트도 그 값을 켜지
 * 않는다. 즉 cron 문자열을 실제로 파싱해 보는 곳이 <b>한 군데도 없다</b> — 표현식이
 * 틀리면 그 사실은 운영에서 {@code LLM_ENABLED=true} 로 뜨는 순간 기동 실패로 처음
 * 드러난다. 스프링 컨텍스트 없이 표현식만 떼어 내 검사한다.</p>
 */
class ConversationSummarySchedulerTest {

    @Test
    @DisplayName("★ 일간 요약 cron 이 파싱되고, 정확히 한 시간 간격으로 돈다")
    void theDailyCronParsesAndFiresEveryHour() throws Exception {
        CronExpression cron = CronExpression.parse(dailyCronFallback());

        LocalDateTime first = cron.next(LocalDateTime.parse("2026-08-06T00:00:00"));
        LocalDateTime second = cron.next(first);

        assertThat(first).isEqualTo(LocalDateTime.parse("2026-08-06T00:20:00"));
        assertThat(Duration.between(first, second))
            .as("창 안의 매시간 틱이 그날의 재시도다 — 하루 한 번이면 놓친 날은 영영 못 채운다")
            .isEqualTo(Duration.ofHours(1));
    }

    @Test
    @DisplayName("★ 애너테이션의 기본값과 LlmProperties 의 기본값이 갈라지지 않는다")
    void theAnnotationFallbackMatchesThePropertyDefault() throws Exception {
        // 기본값이 두 곳에 적히는 구조라(플레이스홀더 + 필드) 조용히 갈라질 수 있다.
        // 갈라지면 yml 을 지운 환경에서만 다른 주기로 돌고, 아무 오류도 나지 않는다.
        assertThat(dailyCronFallback()).isEqualTo(new LlmProperties().getDailySummaryCron());
    }

    @Test
    @DisplayName("일간 요약 틱은 정시를 피한다 — 스케줄러 스레드가 하나뿐이다")
    void theDailyTickDoesNotLandOnTheHour() throws Exception {
        // 대화 요약 스윕(최대 20호출 × 8초)·복약 1분 틱·워치독 3종이 같은 단일 스레드를
        // 쓴다. 정시에 겹치면 이 틱이 통째로 밀리고, 밀린 cron 틱은 재실행되지 않는다.
        LocalDateTime next = CronExpression.parse(dailyCronFallback())
            .next(LocalDateTime.parse("2026-08-06T00:00:00"));
        assertThat(next.getMinute()).isNotZero();
        assertThat(next.getSecond()).isZero();
    }

    /** {@code @Scheduled(cron = "${...:여기}")} 의 기본값만 떼어 낸다. */
    private static String dailyCronFallback() throws NoSuchMethodException {
        Scheduled scheduled = ConversationSummaryScheduler.class
            .getMethod("runDaily")
            .getAnnotation(Scheduled.class);
        String placeholder = scheduled.cron();
        assertThat(placeholder)
            .as("cron 은 재배포 없이 바꿀 수 있도록 반드시 프로퍼티 플레이스홀더여야 한다")
            .startsWith("${bomi.llm.daily-summary-cron:")
            .endsWith("}");
        return placeholder.substring(placeholder.indexOf(':') + 1, placeholder.length() - 1);
    }
}
