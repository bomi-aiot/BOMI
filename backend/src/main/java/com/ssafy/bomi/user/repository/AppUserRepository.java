package com.ssafy.bomi.user.repository;

import com.ssafy.bomi.user.domain.AppUser;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AppUserRepository extends JpaRepository<AppUser, UUID> {
}
