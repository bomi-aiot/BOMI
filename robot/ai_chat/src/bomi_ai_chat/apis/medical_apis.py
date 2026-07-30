# robot/ai_chat/src/bomi_ai_chat/apis/medical_apis.py
import requests
import xmltodict

from bomi_ai_chat.config import Settings, get_settings


class MedicalDataClient:
    def __init__(self, settings: Settings | None = None):
        settings = settings or get_settings()
        self.hospital_key = settings.hira_hospital_api_key
        self.pharmacy_key = settings.hira_pharmacy_api_key
        self.dur_key = settings.dur_prdlst_api_key

    def _get(self, url, params, key, timeout=15):
        query = {
            **params,
            "serviceKey": key,
            "pageNo": params.get("pageNo", 1),
            "numOfRows": params.get("numOfRows", 10),
            "_type": "json",
        }
        resp = requests.get(url, params=query, timeout=timeout)
        resp.raise_for_status()

        try:
            data = resp.json()
        except requests.exceptions.JSONDecodeError:
            data = xmltodict.parse(resp.text)
            data = {"response": data.get("response", data)}

        try:
            body = data["response"]["body"]
            items = body.get("items")
            if not items or isinstance(items, str):
                return []
            return items.get("item", items)
        except (KeyError, TypeError):
            return data

    def get_hospital_info(
        self, sido_cd=None, sgg_cd=None, yadm_nm=None, dgsbjt_cd=None,
        page_no=1, num_of_rows=500,
    ):
        url = "https://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList"
        params = {"pageNo": page_no, "numOfRows": num_of_rows}
        if sido_cd:
            params["sidoCd"] = sido_cd
        if sgg_cd:
            params["sgguCd"] = sgg_cd
        if yadm_nm:
            params["yadmNm"] = yadm_nm
        if dgsbjt_cd:
            params["dgsbjtCd"] = dgsbjt_cd
        return self._get(url, params, self.hospital_key)

    def get_pharmacy_info(
        self,
        sido_cd=None,
        sgg_cd=None,
        emdong_nm=None,
        yadm_nm=None,
        x_pos=None,
        y_pos=None,
        radius=None,
        page_no=1,
        num_of_rows=500,
    ):
        url = "https://apis.data.go.kr/B551182/pharmacyInfoService/getParmacyBasisList"
        params = {"pageNo": page_no, "numOfRows": num_of_rows}
        if sido_cd:
            params["sidoCd"] = sido_cd
        if sgg_cd:
            params["sgguCd"] = sgg_cd
        if emdong_nm:
            params["emdongNm"] = emdong_nm
        if yadm_nm:
            params["yadmNm"] = yadm_nm
        if x_pos:
            params["xPos"] = x_pos
        if y_pos:
            params["yPos"] = y_pos
        if radius:
            params["radius"] = radius
        return self._get(url, params, self.pharmacy_key)

    def get_drug_permission_list(self, page_no=1, num_of_rows=500, item_name=None):
        """의약품 제품허가정보 목록조회 (배치용)"""
        url = "https://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnInq07"
        params = {"pageNo": page_no, "numOfRows": num_of_rows}
        if item_name:
            params["item_name"] = item_name
        return self._get(url, params, self.dur_key)
