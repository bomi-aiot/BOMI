package com.ssafy.bomi.person.web;

import com.ssafy.bomi.person.domain.KnownPerson;
import com.ssafy.bomi.person.repository.KnownPersonRepository;
import com.ssafy.bomi.person.web.dto.KnownPersonDto;
import com.ssafy.bomi.person.web.dto.KnownPersonRequests.CreateKnownPersonRequest;
import com.ssafy.bomi.person.web.dto.KnownPersonRequests.UpdateKnownPersonRequest;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * 명부(known_person) 조회·등록·수정·삭제 서비스. 단일 어르신 전제(P0), 다른
 * 가디언 API(CareRecordCommandService 등)와 같은 패턴이다.
 *
 * <p>화면(FE)은 이 티켓 범위가 아니다(별도 티켓 S15P11E102-327). 여기는 BE API
 * 까지만 닫는다.</p>
 */
@Service
public class KnownPersonService {

    private static final String SENIOR_USER_TYPE = "SENIOR";

    private final AppUserRepository appUserRepository;
    private final KnownPersonRepository knownPersonRepository;

    public KnownPersonService(
            AppUserRepository appUserRepository, KnownPersonRepository knownPersonRepository) {
        this.appUserRepository = appUserRepository;
        this.knownPersonRepository = knownPersonRepository;
    }

    @Transactional(readOnly = true)
    public List<KnownPersonDto> getKnownPersons() {
        return knownPersonRepository.findBySeniorId(seniorId()).stream()
                .map(KnownPersonService::toDto)
                .toList();
    }

    @Transactional
    public KnownPersonDto createKnownPerson(CreateKnownPersonRequest request) {
        KnownPerson person = KnownPerson.register(
                seniorId(),
                null, // 보호자 인증이 아직 없어(§25 열린 결정) 등록자 id 를 알 수 없다. 온보딩과 동일하게 null.
                request.displayName(),
                request.relationship(),
                request.isDeceased(),
                request.deceasedNote(),
                request.livesWith(),
                request.contactFrequency());
        knownPersonRepository.save(person);
        return toDto(person);
    }

    @Transactional
    public KnownPersonDto updateKnownPerson(UUID id, UpdateKnownPersonRequest request) {
        KnownPerson person = load(id);
        person.updateDetails(
                request.displayName(),
                request.relationship(),
                request.isDeceased(),
                request.deceasedNote(),
                request.livesWith(),
                request.contactFrequency());
        knownPersonRepository.save(person);
        return toDto(person);
    }

    @Transactional
    public String deleteKnownPerson(UUID id) {
        KnownPerson person = load(id);
        // care_record 와 달리 이 표는 버전 이력을 남기지 않는다 — 회피 명부는 "지금
        // 시점의 판단"만 의미가 있고, 지워진 항목을 남겨 둘수록 오래된 회피 문구가
        // 실수로 되살아날 표면적만 늘어난다. 그래서 상태 전이가 아니라 실제 삭제다.
        knownPersonRepository.delete(person);
        return id.toString();
    }

    private UUID seniorId() {
        return appUserRepository.findFirstByUserType(SENIOR_USER_TYPE)
                .orElseThrow(() -> new IllegalStateException("등록된 어르신이 없습니다."))
                .getId();
    }

    private KnownPerson load(UUID id) {
        return knownPersonRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "명부 항목을 찾을 수 없습니다: " + id));
    }

    private static KnownPersonDto toDto(KnownPerson person) {
        return new KnownPersonDto(
                person.getId().toString(),
                person.getDisplayName(),
                person.getRelationship(),
                person.getIsDeceased(),
                person.getDeceasedNote(),
                person.getLivesWith(),
                person.getContactFrequency(),
                iso(person.getCreatedAt()),
                iso(person.getUpdatedAt()));
    }

    private static String iso(OffsetDateTime value) {
        return value == null ? null : value.toString();
    }
}
