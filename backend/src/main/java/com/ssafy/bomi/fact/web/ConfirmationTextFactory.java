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
                    String current = medicationLabel(candidate.getConfirmedValue());
                    String next = medicationLabel(proposed);
                    return new ConfirmationText(
                            "복약 정보가 기존과 달라요",
                            "기존 " + orUnknown(current) + " → 대화 인식 " + orUnknown(next),
                            "로봇이 어르신께 복약 시간을 다시 여쭐까요?",
                            "현재 기록: " + orUnknown(current) + " · 대화 인식: " + orUnknown(next) + " · 임의 변경 안 함");
                }
                String label = medicationLabel(proposed);
                return new ConfirmationText(
                        "복약 정보를 확인해 주세요",
                        orUnknown(label) + " 복약 정보를 감지했습니다.",
                        "이 복약 정보를 저장할까요?",
                        "로봇 대화에서 복약 표현 감지");
            }
            if (factType.contains("SCHEDULE") || factType.contains("APPOINTMENT")) {
                String title = str(proposed, "title");
                String startsAt = str(proposed, "startsAt");
                return new ConfirmationText(
                        "일정을 확인해 주세요",
                        "'" + orUnknown(title) + "'을(를) " + orUnknown(startsAt) + " 일정으로 감지했습니다.",
                        orUnknown(startsAt) + " 일정으로 저장할까요?",
                        "로봇 대화에서 일정 표현 감지");
            }
            if (factType.contains("HEALTH")) {
                String title = str(proposed, "title");
                String note = str(proposed, "note");
                return new ConfirmationText(
                        "건강 상태를 기록할까요?",
                        note != null ? "'" + note + "'라고 말씀하셨습니다." : orUnknown(title) + " 관련 관찰이 감지되었습니다.",
                        orUnknown(title) + " 건강 관찰로 남길까요?",
                        "사용자 직접 발화");
            }
        }

        // PROFILE / CARE_RELATIONSHIP / 기타
        return new ConfirmationText(
                "정보를 확인해 주세요",
                "대화에서 새로운 정보가 감지되었습니다.",
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
        return v == null ? null : v.toString();
    }

    private static String orUnknown(String value) {
        return value == null ? "정보 없음" : value;
    }
}
