package com.ssafy.bomi.user.repository;

import com.ssafy.bomi.user.domain.AppUser;
import jakarta.persistence.LockModeType;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface AppUserRepository extends JpaRepository<AppUser, UUID> {

    /** Shared admission lock for every scenario started for one senior. */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select u from AppUser u where u.id = :id")
    Optional<AppUser> findByIdForUpdate(@Param("id") UUID id);

    /** 단일 어르신 전제(P0): user_type = 'SENIOR' 인 첫 사용자. */
    Optional<AppUser> findFirstByUserType(String userType);
}
