package com.ssafy.bomi.scenario.repository;

import com.ssafy.bomi.scenario.domain.Scenario;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ScenarioRepository extends JpaRepository<Scenario, UUID> {
}
