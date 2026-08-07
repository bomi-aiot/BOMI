package com.ssafy.bomi.person.web;

import com.ssafy.bomi.person.web.dto.KnownPersonDto;
import com.ssafy.bomi.person.web.dto.KnownPersonRequests.CreateKnownPersonRequest;
import com.ssafy.bomi.person.web.dto.KnownPersonRequests.UpdateKnownPersonRequest;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 가디언 웹 명부(known_person) API — 조회 + 등록·수정·삭제. 단일 어르신 전제(P0)라
 * 경로에 elderId 없음. 접두: {@code /api/v1/known-persons}.
 *
 * <p>회피 대상(돌아가신 배우자 등)을 관리하는 화면이 호출한다. 화면(FE) 자체는
 * 별도 티켓(S15P11E102-327)이 맡는다 — 여기는 BE API 까지만.</p>
 */
@RestController
@RequestMapping("/api/v1/known-persons")
@Tag(name = "Guardian Known Person", description = "회피 대상 포함 어르신 주변 인물 명부 — 가디언웹이 호출합니다.")
public class KnownPersonController {

    private final KnownPersonService service;

    public KnownPersonController(KnownPersonService service) {
        this.service = service;
    }

    @GetMapping
    public List<KnownPersonDto> getKnownPersons() {
        return service.getKnownPersons();
    }

    @PostMapping
    public KnownPersonDto createKnownPerson(@RequestBody CreateKnownPersonRequest request) {
        return service.createKnownPerson(request);
    }

    @PutMapping("/{id}")
    public KnownPersonDto updateKnownPerson(
            @PathVariable UUID id, @RequestBody UpdateKnownPersonRequest request) {
        return service.updateKnownPerson(id, request);
    }

    @DeleteMapping("/{id}")
    public Map<String, String> deleteKnownPerson(@PathVariable UUID id) {
        return Map.of("id", service.deleteKnownPerson(id));
    }
}
