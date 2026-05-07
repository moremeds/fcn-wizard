from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreToggles:
    iv_rank: bool = True
    vrp: bool = True
    skew: bool = True
    trend: bool = True
    drawdown: bool = True
    liquidity: bool = True
    crash_history: bool = True


def score_single(metrics, toggles: ScoreToggles = ScoreToggles()) -> tuple[float, list[dict]]:
    rows: list[dict] = []

    def add(factor: str, value, points: float, comment: str) -> None:
        rows.append({"factor": factor, "value": value, "points": points, "comment": comment})

    if toggles.iv_rank and metrics.iv_rank is not None:
        if metrics.iv_rank > 70:
            add("IV Rank", metrics.iv_rank, 2.0, "High IV supports coupon richness.")
        elif metrics.iv_rank > 50:
            add("IV Rank", metrics.iv_rank, 1.0, "Moderate IV richness.")
        elif metrics.iv_rank < 25:
            add("IV Rank", metrics.iv_rank, -0.5, "Low IV may not pay enough coupon.")

    if toggles.vrp and metrics.vrp is not None:
        if metrics.vrp > 0.05:
            add("VRP", metrics.vrp, 2.0, "IV is more than 5 vol points above realized vol.")
        elif metrics.vrp > 0.02:
            add("VRP", metrics.vrp, 1.0, "IV is modestly above realized vol.")
        elif metrics.vrp < -0.02:
            add("VRP", metrics.vrp, -1.0, "Realized vol is above IV, weak setup for selling optionality.")

    if toggles.skew and metrics.put_skew_25d is not None:
        if 0.02 < metrics.put_skew_25d < 0.08:
            add("Put Skew", metrics.put_skew_25d, 1.0, "Skew is present but not extreme.")
        elif metrics.put_skew_25d > 0.10:
            add("Put Skew", metrics.put_skew_25d, -1.0, "Very steep skew implies market is pricing tail risk.")

    if toggles.trend and metrics.above_200dma:
        add("Trend", metrics.above_200dma, 1.0, "Spot is above 200DMA.")

    if toggles.drawdown and metrics.drawdown_3m is not None and metrics.drawdown_3m > -0.15:
        add("3M Drawdown", metrics.drawdown_3m, 0.5, "Recent drawdown is contained.")

    if toggles.liquidity and metrics.stock_adv_usd is not None:
        if metrics.stock_adv_usd > 1e9:
            add("Liquidity", metrics.stock_adv_usd, 1.0, "Stock dollar ADV is very high.")
        elif metrics.stock_adv_usd > 2e8:
            add("Liquidity", metrics.stock_adv_usd, 0.5, "Stock dollar ADV is adequate.")

    if toggles.crash_history and metrics.crash_5y is not None:
        if metrics.crash_5y == 0:
            add("5Y Crash", metrics.crash_5y, 2.0, "No 50% drawdown in lookback.")
        else:
            add("5Y Crash", metrics.crash_5y, -1.0, "A 50% drawdown happened in lookback.")

    return round(sum(row["points"] for row in rows), 2), rows


def score_pair(row: dict) -> tuple[float, list[dict]]:
    rows: list[dict] = []
    score = (row["score_a"] + row["score_b"]) / 2.0
    rows.append({"factor": "Single-name base", "value": score, "points": score, "comment": "Average of the two standalone scores."})

    corr = row.get("corr_60d")
    if corr is not None:
        if corr > 0.7:
            rows.append({"factor": "Correlation", "value": corr, "points": 1.5, "comment": "High correlation reduces dispersion risk."})
        elif corr > 0.5:
            rows.append({"factor": "Correlation", "value": corr, "points": 1.0, "comment": "Moderate correlation support."})
        elif corr < 0.3:
            rows.append({"factor": "Correlation", "value": corr, "points": -1.0, "comment": "Low correlation is dangerous for worst-of notes."})

    stability = row.get("corr_stability")
    if stability is not None:
        if stability < 0.10:
            rows.append({"factor": "Correlation stability", "value": stability, "points": 0.5, "comment": "Correlation regime is stable."})
        elif stability > 0.20:
            rows.append({"factor": "Correlation stability", "value": stability, "points": -0.5, "comment": "Correlation regime is unstable."})

    p_either = row.get("p_ki_either")
    if p_either is not None:
        if p_either < 0.15:
            rows.append({"factor": "Joint KI probability", "value": p_either, "points": 1.5, "comment": "Low probability that either leg hits KI."})
        elif p_either < 0.30:
            rows.append({"factor": "Joint KI probability", "value": p_either, "points": 0.5, "comment": "Moderate worst-of KI risk."})
        elif p_either > 0.50:
            rows.append({"factor": "Joint KI probability", "value": p_either, "points": -1.5, "comment": "High worst-of KI risk."})

    coupon_uplift = row.get("coupon_uplift")
    if coupon_uplift is not None:
        if 1.2 < coupon_uplift < 1.8:
            rows.append({"factor": "Coupon uplift", "value": coupon_uplift, "points": 0.5, "comment": "Worst-of risk adds enough coupon potential without becoming extreme."})
        elif coupon_uplift > 2.5:
            rows.append({"factor": "Coupon uplift", "value": coupon_uplift, "points": -0.5, "comment": "Coupon uplift is high because the pair is much riskier than the safer leg."})

    total = round(sum(item["points"] for item in rows), 2)
    return total, rows


def score_basket(row: dict) -> tuple[float, list[dict]]:
    adapted = {
        "score_a": row.get("score_avg", 0.0),
        "score_b": row.get("score_avg", 0.0),
        "corr_60d": row.get("corr_avg"),
        "corr_stability": row.get("corr_stability"),
        "p_ki_either": row.get("p_ki_either"),
    }
    score, rows = score_pair(adapted)
    if rows:
        rows[0] = {
            "factor": "Basket base",
            "value": row.get("score_avg", 0.0),
            "points": row.get("score_avg", 0.0),
            "comment": "Average of the basket leg scores.",
        }
    return score, rows
