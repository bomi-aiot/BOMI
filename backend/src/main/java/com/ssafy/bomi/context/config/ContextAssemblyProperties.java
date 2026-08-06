package com.ssafy.bomi.context.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Context-assembly tuning dials (prefix {@code bomi.context}).
 *
 * <p>Every number the assembly uses lives here rather than in a method body, so
 * tuning "the robot forgets things" or "the prompt is too long" is a config change
 * and not a logic change. The robot has the same split on its side: environment
 * config and product-judgement constants are separate files.</p>
 *
 * <p>The bounds matter for correctness, not just taste. The MVP ERD specifies 3–10
 * long-term memories and 6–12 raw messages; going above that overloads the prompt,
 * and an overloaded prompt is what makes the robot answer with three facts at once
 * instead of one (CLAUDE.md §14).</p>
 *
 * <pre>
 * bomi:
 *   context:
 *     memory-top-k-min: 3
 *     memory-top-k-max: 10
 *     recency-half-life-days: 30
 *     usage-penalty-half-life-days: 1
 *     usage-penalty-floor: 0.3
 * </pre>
 */
@Component
@ConfigurationProperties(prefix = "bomi.context")
public class ContextAssemblyProperties {

    /**
     * Allowed range for the caller's requested memory count.
     *
     * <p>The robot lowers its own top-k under network or resource pressure — that is
     * the first step of its degradation order — so the API must accept a small value
     * without treating it as an error (CLAUDE.md §18).</p>
     */
    private int memoryTopKMin = 3;

    private int memoryTopKMax = 10;

    private int memoryTopKDefault = 6;

    /** Raw message window, per the ERD's 6–12 recipe. */
    private int recentMessageMin = 6;

    private int recentMessageMax = 12;

    private int recentMessageDefault = 8;

    /** How many relevant summaries to attach. Deliberately small. */
    private int summaryLimit = 3;

    /** How many consented care records to attach. */
    private int careRecordLimit = 5;

    /**
     * Days after which a memory's recency contribution halves.
     *
     * <p>Why recency is weighted at all: without it a knee complaint from six months
     * ago outranks yesterday's, and the robot sounds like it is reading an old file
     * rather than remembering a conversation. Raising this makes the robot dwell on
     * older material; lowering it makes it forget last month.</p>
     */
    private int recencyHalfLifeDays = 30;

    /**
     * Floor applied to the relevance component when no semantic search is available.
     *
     * <p>Without a vector store the only relevance signal is keyword overlap, and a
     * memory with no overlapping keyword would otherwise score zero and never
     * surface. That would silently reduce the robot to "remembers nothing", so an
     * unmatched memory keeps a small baseline and importance/recency decide.</p>
     */
    private double relevanceFloor = 0.2;

    /**
     * Days after which a just-used memory's usage penalty half-recovers.
     *
     * <p>Separate dial from {@link #recencyHalfLifeDays} on purpose (S15P11E102-262).
     * Recency asks "when did we last confirm this fact is true"; this asks "when did we
     * last say this out loud". Conflating them made a just-used memory look like the
     * <em>freshest</em> one and get picked again immediately — CLAUDE.md §17.8 exists to
     * prevent exactly that. Lowering this makes the robot willing to repeat itself sooner;
     * raising it makes a used memory stay suppressed longer.</p>
     */
    private int usagePenaltyHalfLifeDays = 1;

    /**
     * Floor applied to a memory the instant after it was used.
     *
     * <p>Not zero, deliberately. A senior with very few stored memories (the exact state
     * S15P11E102-262 exists to fix — reminiscence seeds start near-empty) must still be
     * able to hear the same memory again in the same conversation turn if it is the only
     * relevant one; zeroing it out would make the robot go silent instead of mildly
     * repetitive. Raising this weakens the anti-repeat effect; lowering it strengthens it.</p>
     */
    private double usagePenaltyFloor = 0.3;

    public int getMemoryTopKMin() {
        return memoryTopKMin;
    }

    public void setMemoryTopKMin(int memoryTopKMin) {
        this.memoryTopKMin = memoryTopKMin;
    }

    public int getMemoryTopKMax() {
        return memoryTopKMax;
    }

    public void setMemoryTopKMax(int memoryTopKMax) {
        this.memoryTopKMax = memoryTopKMax;
    }

    public int getMemoryTopKDefault() {
        return memoryTopKDefault;
    }

    public void setMemoryTopKDefault(int memoryTopKDefault) {
        this.memoryTopKDefault = memoryTopKDefault;
    }

    public int getRecentMessageMin() {
        return recentMessageMin;
    }

    public void setRecentMessageMin(int recentMessageMin) {
        this.recentMessageMin = recentMessageMin;
    }

    public int getRecentMessageMax() {
        return recentMessageMax;
    }

    public void setRecentMessageMax(int recentMessageMax) {
        this.recentMessageMax = recentMessageMax;
    }

    public int getRecentMessageDefault() {
        return recentMessageDefault;
    }

    public void setRecentMessageDefault(int recentMessageDefault) {
        this.recentMessageDefault = recentMessageDefault;
    }

    public int getSummaryLimit() {
        return summaryLimit;
    }

    public void setSummaryLimit(int summaryLimit) {
        this.summaryLimit = summaryLimit;
    }

    public int getCareRecordLimit() {
        return careRecordLimit;
    }

    public void setCareRecordLimit(int careRecordLimit) {
        this.careRecordLimit = careRecordLimit;
    }

    public int getRecencyHalfLifeDays() {
        return recencyHalfLifeDays;
    }

    public void setRecencyHalfLifeDays(int recencyHalfLifeDays) {
        this.recencyHalfLifeDays = recencyHalfLifeDays;
    }

    public double getRelevanceFloor() {
        return relevanceFloor;
    }

    public void setRelevanceFloor(double relevanceFloor) {
        this.relevanceFloor = relevanceFloor;
    }

    public int getUsagePenaltyHalfLifeDays() {
        return usagePenaltyHalfLifeDays;
    }

    public void setUsagePenaltyHalfLifeDays(int usagePenaltyHalfLifeDays) {
        this.usagePenaltyHalfLifeDays = usagePenaltyHalfLifeDays;
    }

    public double getUsagePenaltyFloor() {
        return usagePenaltyFloor;
    }

    public void setUsagePenaltyFloor(double usagePenaltyFloor) {
        this.usagePenaltyFloor = usagePenaltyFloor;
    }
}
