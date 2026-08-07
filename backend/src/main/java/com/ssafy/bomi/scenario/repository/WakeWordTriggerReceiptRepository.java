package com.ssafy.bomi.scenario.repository;

import com.ssafy.bomi.scenario.domain.WakeWordTriggerReceipt;
import org.springframework.data.jpa.repository.JpaRepository;

public interface WakeWordTriggerReceiptRepository
    extends JpaRepository<WakeWordTriggerReceipt, String> {
}
