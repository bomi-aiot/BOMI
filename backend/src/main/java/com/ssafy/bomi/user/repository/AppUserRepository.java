package com.ssafy.bomi.user.repository;

import com.ssafy.bomi.user.domain.AppUser;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AppUserRepository extends JpaRepository<AppUser, UUID> {

    /** 단일 어르신 전제(P0): user_type = 'SENIOR' 인 첫 사용자. */
    Optional<AppUser> findFirstByUserType(String userType);
}
