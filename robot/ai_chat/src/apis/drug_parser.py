# robot/ai_chat/src/apis/drug_parser.py
"""의약품 제품허가정보 API 응답을 필요한 필드만 정제하는 파서."""
import re

PILL_FORM_KEYWORDS = {
    "정제": ["정제", "필름코팅정", "나정", "장용정"],
    "캡슐": ["캡슐"],
    "주사제": ["주사", "앰플", "바이알"],
    "시럽/액상": ["시럽", "액", "용액"],
    "기타": [],
}


def classify_pill_form(chart_text: str) -> str:
    """CHART(성상) 텍스트에서 약 형태를 분류한다."""
    if not chart_text:
        return "기타"
    for form, keywords in PILL_FORM_KEYWORDS.items():
        if any(kw in chart_text for kw in keywords):
            return form
    return "기타"


def extract_dosage_text(ud_doc_data: str) -> str:
    """UD_DOC_DATA의 XML 태그를 제거하고 순수 텍스트만 추출한다."""
    if not ud_doc_data:
        return ""
    cdata_matches = re.findall(r"<!\[CDATA\[(.*?)\]\]>", ud_doc_data, re.DOTALL)
    if cdata_matches:
        return " ".join(m.strip() for m in cdata_matches)
    return re.sub(r"<[^>]+>", " ", ud_doc_data).strip()


def parse_drug_item(raw: dict) -> dict:
    """API 원본 응답 하나를 필요한 필드만 추출해 정제한다."""
    return {
        "item_seq": raw.get("ITEM_SEQ"),
        "item_name": raw.get("ITEM_NAME"),
        "pill_form": classify_pill_form(raw.get("CHART")),
        "dosage_text": extract_dosage_text(raw.get("UD_DOC_DATA")),
        "storage_method": raw.get("STORAGE_METHOD"),
        "etc_otc": raw.get("ETC_OTC_CODE"),
        "entp_name": raw.get("ENTP_NAME"),
    }