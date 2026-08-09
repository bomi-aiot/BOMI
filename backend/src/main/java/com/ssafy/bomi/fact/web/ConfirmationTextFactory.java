package com.ssafy.bomi.fact.web;

import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactOperation;
import com.ssafy.bomi.fact.domain.FactTargetDomain;
import java.util.Map;
import java.util.Objects;
import org.springframework.stereotype.Component;

/**
 * fact_candidate 로부터 보호자에게 보여줄 표시 문구(title/summary/question/evidence)를 생성한다.
 * 이 값들은 DB 컬럼이 아니며 저장하지 않는다(매 응답 생성). BE 계약 문서(§2) 템플릿 기반.
 */
@Component
public class ConfirmationTextFactory {

    /** 생성된 표시 문구 묶음. */
    public record ConfirmationText(String title, String summary, String question, String evidence) {
    }

    public ConfirmationText create(FactCandidate candidate) {
        FactTargetDomain domain = candidate.getTargetDomain();
        String factType = candidate.getFactType() == null ? "" : candidate.getFactType().toUpperCase();
        Map<String, Object> proposed = candidate.getProposedValue();

        if (domain == FactTargetDomain.MEMORY) {
            String content = str(proposed, "content");
            String keyword = firstKeyword(proposed);
            return new ConfirmationText(
                    "새로운 관심사로 저장할까요?",
                    content != null ? content : (keyword != null ? keyword + " 관련 이야기가 반복되었습니다." : "새로운 관심사가 감지되었습니다."),
                    (keyword != null ? keyword : "이 관심사") + "을(를) 계속 활용할까요?",
                    "최근 대화에서 감지");
        }

        if (domain == FactTargetDomain.CARE_RECORD) {
            if (factType.startsWith("MEDICATION")) {
                if (candidate.getOperation() == FactOperation.UPDATE) {
                    // 여기서의 "없음" 은 값을 못 읽었다는 뜻이 아니라 기록이 없다는
                    // 사실이다 — 그래서 "정보 없음"(= 표시 실패처럼 읽힌다)이 아니라
                    // "기록 없음" 으로 적는다.
                    String current = firstNonBlank(medicationLabel(candidate.getConfirmedValue()), "기록 없음");
                    String next = firstNonBlank(
                            medicationLabel(proposed), str(proposed, "content"), "내용 확인 필요");
                    return new ConfirmationText(
                            "복약 정보가 기존과 달라요",
                            "기존 " + current + " → 대화 인식 " + next,
                            "로봇이 어르신께 복약 시간을 다시 여쭐까요?",
                            "현재 기록: " + current + " · 대화 인식: " + next + " · 임의 변경 안 함");
                }
                String label = firstNonBlank(medicationLabel(proposed), str(proposed, "content"));
                return new ConfirmationText(
                        "복약 정보를 확인해 주세요",
                        label != null
                                ? "'" + label + "' 복약 정보를 감지했습니다."
                                : "복약 관련 이야기를 들었어요.",
                        "이 복약 정보를 저장할까요?",
                        "로봇 대화에서 복약 표현 감지");
            }
            if (factType.contains("SCHEDULE") || factType.contains("APPOINTMENT")) {
                String title = firstNonBlank(str(proposed, "title"), str(proposed, "content"));
                String startsAt = str(proposed, "startsAt");
                return new ConfirmationText(
                        "일정을 확인해 주세요",
                        title != null
                                ? "'" + title + "'을(를) 일정으로 감지했습니다."
                                        + (startsAt == null ? " 시각은 아직 확인하지 못했어요." : " (" + startsAt + ")")
                                : "일정으로 보이는 이야기를 들었어요.",
                        startsAt != null
                                ? startsAt + " 일정으로 저장할까요?"
                                : "시각을 확인한 뒤 일정으로 저장할까요?",
                        "로봇 대화에서 일정 표현 감지");
            }
            if (factType.contains("HEALTH")) {
                // ★ content 를 읽는다 — 이 분기가 실제로 받는 유일한 키다.
                //
                //   로봇은 건강 발화를 {"content": "..."} 하나로만 보낸다
                //   (ai_chat fact_contract.to_intake_payload — note/title 을 채우는
                //   경로는 APPOINTMENT 뿐이다). 그래서 note/title 만 읽던 이전 코드는
                //   두 값이 항상 null 이었고, orUnknown 이 그 자리를 "정보 없음" 으로
                //   채웠다 — 보호자는 "정보 없음 관련 관찰이 감지되었습니다" 라는,
                //   어르신이 무슨 말을 했는지 한 글자도 없는 문장을 받았다.
                //
                //   note 를 먼저 보는 순서는 유지한다. 온보딩 답변 경로는 note 를
                //   채워 보낼 수 있고, 그쪽이 더 정제된 값이다.
                String title = str(proposed, "title");
                String note = str(proposed, "note");
                String content = str(proposed, "content");
                String said = firstNonBlank(note, content);
                return new ConfirmationText(
                        "건강 상태를 기록할까요?",
                        said != null
                                ? "'" + said + "'라고 말씀하셨습니다."
                                : "건강 관련 관찰이 감지되었습니다.",
                        // 제목이 따로 없으면 문장을 한 번 더 되뇌지 않는다 — 바로 위
                        // summary 에 이미 그 말이 있고, 화면은 둘을 붙여 놓는다.
                        title != null
                                ? "'" + title + "' 건강 관찰로 남길까요?"
                                : "이 내용을 건강 관찰로 남길까요?",
                        "사용자 직접 발화");
            }
        }

        // PROFILE / CARE_RELATIONSHIP / 기타
        String content = str(proposed, "content");
        return new ConfirmationText(
                "정보를 확인해 주세요",
                content != null
                        ? "'" + content + "'라고 말씀하셨습니다."
                        : "대화에서 새로운 정보가 감지되었습니다.",
                "이 정보를 반영할까요?",
                "로봇 대화에서 감지");
    }

    private static String medicationLabel(Map<String, Object> value) {
        if (value == null) {
            return null;
        }
        String name = str(value, "medicationName");
        String localTime = str(value, "localTime");
        if (localTime == null) {
            Object localTimes = value.get("localTimes");
            if (localTimes instanceof Iterable<?> iterable) {
                for (Object t : iterable) {
                    localTime = Objects.toString(t, null);
                    break;
                }
            }
        }
        if (name == null && localTime == null) {
            return null;
        }
        if (localTime == null) {
            return name;
        }
        return (name == null ? "복약" : name) + " " + localTime;
    }

    private static String firstKeyword(Map<String, Object> value) {
        if (value == null) {
            return null;
        }
        Object keywords = value.get("keywords");
        if (keywords instanceof Iterable<?> iterable) {
            for (Object k : iterable) {
                return Objects.toString(k, null);
            }
        }
        return str(value, "title");
    }

    private static String str(Map<String, Object> value, String key) {
        if (value == null) {
            return null;
        }
        Object v = value.get(key);
        if (v == null) {
            return null;
        }
        String text = v.toString().trim();
        return text.isEmpty() ? null : text;
    }

    /**
     * 앞에서부터 비어 있지 않은 첫 값. 전부 비면 null.
     *
     * <p>이 클래스에 있던 {@code orUnknown} 을 대신한다. 그쪽은 값이 없을 때 "정보 없음"
     * 이라는 <em>글자</em>를 문장 한가운데에 끼워 넣었고, 그래서 키 하나가 어긋나면
     * "정보 없음 관련 관찰이 감지되었습니다" 같은, 문법은 멀쩡하고 내용은 하나도 없는
     * 문장이 보호자 화면까지 그대로 나갔다 — 값을 못 읽었다는 사실이 문장 안에 숨는다.
     * 값이 없으면 값을 끼워 넣지 말고 문장 자체를 바꾸는 것이 옳다.</p>
     */
    private static String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return null;
    }
}
