package com.ssafy.bomi.context.application;

import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Component;

/**
 * Stand-in used until the external vector store is wired up (S15P11E102-218).
 *
 * <p>Returns no candidates and reports itself unavailable. The assembly then ranks
 * memories by keyword overlap, importance, and recency — the non-vector half of the
 * ERD's stated mix ("keywords 정확 일치와 embedding 의미 검색을 혼합"). Retrieval keeps
 * working; it is just shallower.</p>
 *
 * <p>It reports {@code isAvailable() == false} rather than pretending, because the
 * failure this prevents is subtle: a caller that believes it received semantically
 * ranked memories has no reason to doubt them, and nobody notices the robot has
 * quietly stopped making connections across conversations.</p>
 *
 * <p><strong>How to replace it (S15P11E102-218):</strong> annotate the real
 * implementation {@code @Primary} so it wins, or delete this class. Registering a
 * second unmarked implementation fails at startup with "expected single matching bean",
 * which is the intended outcome — a loud failure beats two search paths disagreeing.</p>
 *
 * <p>Deliberately <em>not</em> {@code @ConditionalOnMissingBean}: that annotation only
 * behaves predictably inside auto-configuration, and on a scanned {@code @Component} it
 * can leave no bean at all.</p>
 */
@Component
public class NoVectorStoreMemorySearch implements MemorySemanticSearch {

    @Override
    public List<SemanticHit> search(UUID seniorId, String query, int limit) {
        return List.of();
    }

    @Override
    public boolean isAvailable() {
        return false;
    }
}
