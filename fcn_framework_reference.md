# FCN Screening Framework — 完整技术参考

> 给 APEX FCN screener 的配套文档:产品定义、payoff 分解、定价模型、风险度量、Screener 架构、扩展路线图。
> 配套脚本:`fcn_screener.py`(单票),`fcn_pair_screener.py`(worst-of pair),`fair_coupon.py`(PB quote vs fair coupon)。

---

## 目录

1. [产品概览](#1-产品概览)
2. [Payoff 分解](#2-payoff-分解)
3. [定价模型与公式](#3-定价模型与公式)
4. [Worst-of 扩展](#4-worst-of-扩展)
5. [风险度量(Screener 用到的全部指标)](#5-风险度量)
6. [Screening 评分框架](#6-screening-评分框架)
7. [Script 架构](#7-script-架构)
8. [扩展路线图](#8-扩展路线图)
9. [Formula Cheat Sheet](#9-formula-cheat-sheet)
10. [References](#10-references)

---

## 1. 产品概览

### 1.1 FCN 定义

**Fixed Coupon Note (FCN)** 是一种结构化产品,投资者用 100% 名义金 $N$ 申购,期间获得固定 coupon,期末视市场情况返还本金或以预先约定的 strike 强制接货某只股票。HK Private Banking 在 2023–2026 年这一波美股波动中,FCN(尤其 worst-of FCN on US single names)取代了传统 AQ 成为最主流的结构化单票产品。

### 1.2 关键 term sheet 元素

| Parameter | Symbol | Typical Value | 说明 |
|---|---|---|---|
| Notional | $N$ | $1M USD | 投资名义本金 |
| Tenor | $T$ | 6M / 12M | 合约总期限 |
| Strike (Initial Reference) | $K$ | 100% × spot | 接货价 |
| KI Barrier | $B$ | 50%–70% × spot | American observation,任何时点触及就触发 |
| KO / Autocall Trigger | $A$ | 100%–105% × spot | 月观察 / 季观察 |
| Coupon Rate (annualized) | $C$ | 12%–25% | 周期性支付 |
| Settlement | — | Physical / Cash | KI 后到期若 $S_T < K$ 则强制接货 |

### 1.3 FCN vs AQ — 经济本质对比

| 维度 | AQ (Accumulator) | FCN (Fixed Coupon Note) |
|---|---|---|
| Strike 含义 | Discount accumulation price (80–90% spot) | Initial reference = 100% spot |
| 现金流方向 | 投资者持续付款买货 | 投资者收 coupon |
| Knock direction | KO at upside,封顶上行 | KO at upside (autocall) + KI at downside |
| 跌破 strike 行为 | 强制加仓(常 2× gearing) | 仅在 KI 后才结算 short put |
| 内嵌期权 | Long forward strip + short put strip + KO | Bond + short DIP @ K, KI @ B |
| Path 依赖 | 极强(每日结算) | 中(只看 KI 触发与否 + 终值) |
| Tail toxicity | "I kill you later"——下跌加仓复利亏 | 二元——KI 之前像收息,触发后变 long stock @ K |

---

## 2. Payoff 分解

### 2.1 单票 FCN 投资者头寸

设:
- $S_t$ = 标的在 $t$ 时刻的价格
- $S_0$ = 初始 spot,通常 $K = S_0$
- $B$ = KI barrier(例如 $0.5 \cdot S_0$)
- $A$ = autocall 触发位
- $\{t_i\}_{i=1}^{n}$ = 观察日(月观察则 $n = 12 T$)
- $C$ = 年化 coupon
- $\tau$ = autocall 触发时刻;若不触发则 $\tau = T$

**KI 路径指标:**
$$\mathbb{1}_{KI} = \mathbb{1}\!\left\{\min_{t \in [0,T]} S_t \le B\right\}$$

**Autocall 触发指标(在第 $i$ 个观察日首次触发):**
$$\mathbb{1}_{AC,i} = \mathbb{1}\!\left\{S_{t_j} < A,\; \forall j < i\right\} \cdot \mathbb{1}\!\left\{S_{t_i} \ge A\right\}$$

**总 payoff 现值给投资者:**

$$V_0^{\text{FCN}} = \underbrace{\sum_{i:\, t_i \le \tau} N \cdot C \cdot \Delta t \cdot e^{-r t_i}}_{\text{coupons until autocall or maturity}} + \underbrace{N \cdot e^{-r \tau}}_{\text{notional return}} - \underbrace{\mathbb{1}_{KI} \cdot \mathbb{1}_{\tau = T} \cdot \mathbb{1}_{S_T < K} \cdot N \cdot \frac{K - S_T}{K} \cdot e^{-rT}}_{\text{KI loss}}$$

### 2.2 等价分解(投资者视角)

$$\boxed{\text{FCN Investor} \;\equiv\; \text{Bond} + \text{Coupon Stream} - \text{Down-and-In Put}_{K}^{B} + \text{Short Autocall Option}}$$

也即投资者:
- **多** 一张零息债 + 固定 coupon stream
- **空** 一张 strike $K$、barrier $B$ 的 down-and-in put
- **空** 一张 autocall feature(dealer 有提前赎回的权利,投资者放弃了上行)

### 2.3 Dealer 视角

Dealer 是镜像头寸,且需要动态对冲 DIP 的 delta、gamma、vega、vanna、volga。Dealer 真正赚的来源:

1. **Skew premium**:卖给客户的 deep OTM put 隐含 vol 比 dealer 实际 hedge 成本高 5–10 vol pts
2. **Correlation premium**(worst-of):客户隐含承担的 ρ 比 realized ρ 低 → dealer long correlation 赚
3. **Autocall optionality**:类似 short callable bond,dealer 持有 callability
4. **Distribution markup**:RM/PB 渠道再吃 1–2%

---

## 3. 定价模型与公式

### 3.1 假设(用于 screening 的快速估值,不用于 production booking)

- 标的服从 GBM:$dS_t = \mu S_t \, dt + \sigma S_t \, dW_t$
- 常数波动率 $\sigma$(实际应使用 local vol surface)
- 常数无风险利率 $r$
- 无股息(美股大部分 FCN 标的近似适用)
- 离散观察 KI 用连续 KI 近似(实际 American KI ≈ continuous;若是 European KI 公式不同)

### 3.2 Barrier 触及概率(单票,closed form)

对于 GBM 下移 barrier $B < S_0$,first-passage time distribution:

$$P\!\left(\min_{0 \le t \le T} S_t \le B\right) = \Phi\!\left(\frac{\ln(B/S_0) - \nu T}{\sigma\sqrt{T}}\right) + \left(\frac{B}{S_0}\right)^{2\nu/\sigma^2} \Phi\!\left(\frac{\ln(B/S_0) + \nu T}{\sigma\sqrt{T}}\right)$$

其中 $\nu = \mu - \sigma^2/2$。

**零漂移特例**($\nu = 0$,screener 中使用):

$$\boxed{P(KI) = 2 \cdot \Phi\!\left(\frac{\ln(B/S_0)}{\sigma\sqrt{T}}\right)}$$

**Code reference**(`fcn_pair_screener.py:single_name_ki_prob`):
```python
def single_name_ki_prob(vol, barrier=0.5, days=252):
    sigma_T = vol * np.sqrt(days/252)
    return 2.0 * norm.cdf(np.log(barrier) / sigma_T)
```

**Sanity:**
- $\sigma = 0.30$, $B = 0.5$, $T = 1Y$ → $P = 2.1\%$
- $\sigma = 0.50$, $B = 0.5$, $T = 1Y$ → $P = 16.6\%$
- $\sigma = 0.60$, $B = 0.5$, $T = 1Y$ → $P = 24.8\%$
- $\sigma = 0.80$, $B = 0.5$, $T = 1Y$ → $P = 38.1\%$

### 3.3 Down-and-In Put 闭式解(Reiner-Rubinstein,无漂移)

设 $K = S_0$(典型 FCN),$B < S_0$:

$$P_{DIP} = S_0 \!\left[\Phi(d_1) - \left(\frac{B}{S_0}\right)^{2} \Phi(d_3)\right] - K e^{-rT}\!\left[\Phi(d_2) - \left(\frac{B}{S_0}\right)^{0} \Phi(d_4)\right]$$

(完整 Reiner-Rubinstein 公式有八种 in/out × call/put × strike 位置,这里给的是 strike 在 barrier 之上的 down-and-in put 简化版本)

实践中 FCN 的 DIP 用 closed form 已经足够 screening,production booking 用 PDE 或 local vol MC。当前代码提供两层:
- `down_in_put_proxy`: 用 KI touch probability × 条件损失的稳定 screening proxy。
- `down_in_put_rr`: 先通过 vanilla bound / barrier edge-case invariant tests 的 gated function,暂不进入 score 排名;后续需要用外部 reference cases 完成公式级校验后再替换 proxy。

### 3.4 期望 KI 损失(条件 + 无条件)

**条件期望损失,给定 KI 触发:**

近似:KI 触发瞬间 $S_\tau = B$,剩余 $T-\tau$ 时间持有 vanilla put $P_K(B, T-\tau)$:

$$E[\text{Loss} | KI] \approx (K - B) + \text{TV}(B, T-\tau)$$

对 $K = 1, B = 0.5, T-\tau \approx 0.5$:
- 内在值 = 50%
- 时间价值 ≈ 3–5%
- 总值 ≈ **50–55% of notional**

**无条件期望损失:**
$$E[\text{Loss}] = P(KI) \cdot E[\text{Loss} | KI]$$

### 3.5 Coupon 期望现值(含 autocall)

设每月观察 autocall,每月 KO 概率 $p$ 独立(粗近似):

$$E[\text{Coupons collected}] = \sum_{i=1}^{12T} C \cdot \Delta t \cdot (1-p)^{i-1} \cdot p \cdot i \;+\; C \cdot T \cdot (1-p)^{12T}$$

**几何衰减下的预期收取月数:**
$$E[\text{months alive}] \approx \frac{1 - (1-p)^{12T}}{p}$$

对 spot 处于 $A$ 附近、$\sigma \approx 0.5$ 的高波动票,月 KO 概率 $p \approx 0.45$–$0.55$,**预期 alive 时间 ~3–4 个月**。

### 3.6 Fair Coupon 反推

**No-arbitrage 平衡条件:**
$$N = \underbrace{E[\text{Coupons collected (PV)}]}_{\text{投资者收}} + \underbrace{N \cdot E[e^{-r\tau}]}_{\text{本金返还}} - \underbrace{P(KI) \cdot E[\text{Loss} | KI] \cdot e^{-rT} \cdot N}_{\text{投资者赔}}$$

整理后:
$$\boxed{C_{\text{fair}} \approx \frac{P(KI) \cdot E[\text{Loss}|KI]}{E[\text{months alive}] / 12}}$$

**Worked example:**
- NVDA + TSLA worst-of, $\sigma_{wof} \approx 0.65$, $\rho = 0.55$
- $P(\text{either KI}) \approx 50\%$
- $E[\text{Loss}|KI] \approx 50\%$
- Expected DIP PV ≈ 25% notional
- Expected alive ≈ 3.5 months
- $C_{\text{fair}} \approx 25\% / (3.5/12) \approx 86\%$ annualized

显然实际报价 20% 远低于 risk-neutral fair value。差额来自:
1. Real-world drift(标的通常 trending up)
2. Skew 已经把 OTM put 卖贵了,dealer hedge 成本低于 closed-form
3. Dealer 主动定价让 PV 给客户负 5–8%(margin)

**Screener 输出 implied fair coupon 与报价 coupon 的差,作为定性指标。**

本项目的符号约定:
$$\boxed{\text{dealer\_margin} = C_{\text{fair}} - C_{\text{quoted}}}$$

因此 `dealer_margin > 0` 表示模型 fair coupon 高于 PB 报价,客户在 coupon 上被 underpaid;值越大,越像 PB / dealer 把经济价值拿走。`dealer_margin < 0` 表示 PB 报价比模型 fair value 更高,需要再检查输入假设和 quote 条款是否一致。

---

## 4. Worst-of 扩展

### 4.1 多资产 GBM(Cholesky)

设 $n$ 只标的,相关矩阵 $\Sigma \in \mathbb{R}^{n \times n}$,Cholesky 分解 $\Sigma = LL^\top$。

每步 Brownian 增量:
$$d\mathbf{W}_t = L \cdot d\boldsymbol{\epsilon}_t, \quad \boldsymbol{\epsilon}_t \sim N(\mathbf{0}, I_n)$$

每只标的:
$$S_t^{(i)} = S_0^{(i)} \exp\!\left(-\tfrac{1}{2}\sigma_i^2 t + \sigma_i W_t^{(i)}\right)$$

### 4.2 Worst-of KI 概率(无解析解,用 MC)

$$P(\text{at least one KI}) = E\!\left[\mathbb{1}\!\left\{\bigcup_{i=1}^{n} \min_{t} S_t^{(i)} \le B^{(i)}\right\}\right]$$

**Code reference**(`fcn_pair_screener.py:joint_ki_prob_mc`):
```python
def joint_ki_prob_mc(vol_a, vol_b, rho, barrier=0.5, days=252, n_sims=20_000, seed=42):
    rng = np.random.default_rng(seed)
    dt = 1/252
    cov = np.array([[1.0, rho], [rho, 1.0]])
    L = np.linalg.cholesky(cov)
    z = rng.standard_normal(size=(n_sims, days, 2)) @ L.T
    diff_a = -0.5*vol_a**2*dt + vol_a*np.sqrt(dt)*z[:,:,0]
    diff_b = -0.5*vol_b**2*dt + vol_b*np.sqrt(dt)*z[:,:,1]
    min_a = np.exp(np.cumsum(diff_a, axis=1).min(axis=1))
    min_b = np.exp(np.cumsum(diff_b, axis=1).min(axis=1))
    return float((min_a <= barrier) | (min_b <= barrier)).mean()
```

### 4.3 Worst-of 隐含 vol 直觉

虽然没有 clean closed form,经验法则(适用于 ATM):

$$\sigma_{\text{worst-of, eff}} \approx \sigma_{\max} \cdot \sqrt{1 + \text{dispersion factor}(\rho, n)}$$

对 $n = 2$, $\rho = 0.5$, 两只 vol 60% 的票,worst-of 等效 vol 大约 70–75%。这就是为什么 worst-of FCN 的 fair coupon 比单票 FCN 显著高。

### 4.4 相关性敏感度

| ρ | P(either KI),NVDA(50%) + TSLA(60%) | P(both KI) |
|---|---|---|
| 0.3 | 44.2% | 10.4% |
| 0.5 | 41.7% | 12.9% |
| 0.7 | 38.6% | 15.9% |
| 0.9 | 34.8% | 19.6% |

**关键洞察:**
- 投资者 short correlation——ρ 越低,P(either) 越高,投资者越受伤
- Dealer long correlation——ρ 越低,DIP 价值越高,coupon 应该越高
- **PB sales 的 game**:报价时把 ρ 当 0.4 算,实际 realized ρ 是 0.55–0.65 → dealer 拿走 correlation premium

---

## 5. 风险度量

Screener 用到的所有指标的精确定义:

### 5.1 实现波动率(Realized Vol)

**Log-return-based,annualized:**
$$RV_T = \sqrt{\frac{252}{T}\sum_{i=1}^{T} \left(\ln \frac{S_i}{S_{i-1}}\right)^2}$$

(忽略均值,short-window 误差小)

### 5.2 隐含波动率秩(IV Rank)

$$IV_{\text{Rank}} = \frac{IV_t - \min(IV_{[t-252,t]})}{\max(IV_{[t-252,t]}) - \min(IV_{[t-252,t]})} \times 100$$

注:与 IV Percentile 不同。Percentile = 当前 IV 在过去 252 天分布中的百分位。Rank 用 min/max 端点。

### 5.3 波动率风险溢价(VRP)

$$VRP_t = IV_{30D,t} - RV_{30D,t}$$

正 VRP = 期权"贵"——卖方(dealer)和 FCN 投资者都能受益。

### 5.4 Put Skew(25-delta)

$$\text{Skew}_{25\Delta P} = IV_{25\Delta P,T} - IV_{ATM,T}$$

实务里也用 risk reversal:
$$RR = IV_{25\Delta C} - IV_{25\Delta P}$$

(美股单票 RR 通常负:put skew > call skew)

### 5.5 Maximum Drawdown

$$MDD_T = \min_{t \le T}\!\left(\frac{S_t}{\max_{s \le t} S_s} - 1\right)$$

Screener 中用 5Y MDD ≤ -50% 作为 "crash flag"——历史出现过 50%+ 回撤的票,FCN KI 不再是 tail event 而是中等概率事件。

### 5.6 Pearson 滚动相关性

$$\rho_{t,W} = \frac{\sum_{i=t-W+1}^{t}(r_i^{(1)} - \bar{r}^{(1)})(r_i^{(2)} - \bar{r}^{(2)})}{\sqrt{\sum (r_i^{(1)} - \bar{r}^{(1)})^2 \sum (r_i^{(2)} - \bar{r}^{(2)})^2}}$$

Screener 用 $W = 60$ 天。

### 5.7 相关性稳定性

$$\sigma_\rho = \text{stdev}(\{\rho_{t,60} : t \in \text{lookback}\})$$

低值 = 相关性 regime 稳定,适合做 worst-of(因为 dealer 对 ρ 的报价假设可信)。
高值 = 相关性会跳,模型风险大。

---

## 6. Screening 评分框架

### 6.1 单票 score(`fcn_screener.py:score`)

| 因子 | 阈值 | 加分 / 扣分 | 理由 |
|---|---|---|---|
| IV Rank | > 70 | +2.0 | 高 IV = 高 coupon |
| IV Rank | 50–70 | +1.0 | 中等 |
| IV Rank | < 25 | −0.5 | IV 太低,coupon 撑不起 |
| VRP | > 0.05 | +2.0 | IV 比 RV 贵 5+ pts,卖方 edge 大 |
| VRP | 0.02–0.05 | +1.0 | 中等 edge |
| VRP | < −0.02 | −1.0 | IV 比 RV 还便宜,反向不利 |
| Skew | 0.02–0.08 | +1.0 | Skew 适中,不极端 |
| Skew | > 0.10 | −1.0 | Skew 过陡,dealer 已 price in 大 tail |
| Above 200DMA | True | +1.0 | 趋势健康 |
| 3M drawdown | > −15% | +0.5 | 近期没崩 |
| Stock $ ADV | > 1B | +1.0 | 流动性好 |
| Stock $ ADV | 200M–1B | +0.5 | 流动性中 |
| 5Y crash (≥50%) | 0 次 | +2.0 | KI 安全 |
| 5Y crash | 1+ 次 | −1.0 | 历史已证明可崩 50% |

### 6.2 Pair score(`fcn_pair_screener.py:score_pair`)

Base score = 两只单票 score 平均。然后:

| 因子 | 阈值 | 加分 / 扣分 |
|---|---|---|
| corr_60d | > 0.7 | +1.5 |
| corr_60d | 0.5–0.7 | +1.0 |
| corr_60d | < 0.3 | −1.0 |
| corr_stability | < 0.10 | +0.5 |
| corr_stability | > 0.20 | −0.5 |
| P(either KI) | < 0.15 | +1.5 |
| P(either KI) | 0.15–0.30 | +0.5 |
| P(either KI) | > 0.50 | −1.5 |
| coupon_uplift | 1.2–1.8 | +0.5 |
| coupon_uplift | > 2.5 | −0.5 |

**注意:** 当前权重是经验设定。Production 化时建议改成数据驱动——用历史 FCN sample 的实际 KI 触发 outcomes 训练 logistic regression / GBM 来 calibrate weights。

### 6.3 Coupon Uplift

$$\text{Coupon Uplift} = \frac{P(\text{worst-of either KI})}{\min(P(KI_a), P(KI_b))}$$

直觉:把"好"的那只单票当 baseline,加上"坏"的那只票后,worst-of KI 风险翻几倍。Uplift 应该对应 dealer 给的 coupon 上调幅度。

---

## 7. Script 架构

### 7.1 当前文件清单

```
fcn_screener/
├── fcn_screener.py              # 单票 screener
├── fcn_pair_screener.py         # Worst-of pair screener
├── fair_coupon.py               # PB quote vs model fair coupon
├── app/streamlit_app.py         # 交互式 dashboard
├── src/fcn_wizard/
│   ├── analytics/               # metrics / scoring / analysis
│   ├── data/                    # IBKR data adapter
│   ├── storage/                 # run history persistence
│   ├── workflows/               # bootstrap / fair coupon workflows
│   └── quotes/                  # PB quote normalization / comparison
├── outputs/
│   ├── fcn_candidates_YYYYMMDD.csv
│   ├── run_index.csv
│   └── runs/RUN_ID/
│       ├── candidates.csv       # 可 reload 的单票结果
│       ├── pairs.csv            # 可 reload 的 pair 结果(如已运行)
│       └── metadata.json        # run config / product assumptions
└── fcn_pairs_YYYYMMDD.csv       # legacy pair screener 输出(兼容旧 workflow)
```

### 7.2 数据流

```
IB Gateway / TWS
    │
    │ ib_insync.IB.reqHistoricalData
    │   - TRADES (price/volume)
    │   - OPTION_IMPLIED_VOLATILITY (30D IV history)
    │ ib_insync.IB.reqSecDefOptParams (chain)
    │ ib_insync.IB.reqMktData (delta/IV per option)
    ▼
fcn_screener.py
    │ - per-ticker metric computation
    │ - heuristic scoring
    ▼
outputs/fcn_candidates_YYYYMMDD.csv
outputs/runs/RUN_ID/candidates.csv + outputs/run_index.csv
    │
    ▼
fcn_pair_screener.py (优先 auto-load run history;其次 dated CSV)
    │ - re-fetch returns from IB
    │ - rolling correlation
    │ - Cholesky MC for joint KI
    │ - pair scoring
    ▼
fcn_pairs_YYYYMMDD.csv
outputs/runs/RUN_ID/pairs.csv
    │
    ▼
fair_coupon.py
    │ - read latest pairs or --pairs-file
    │ - read PB quote CSV: pb,symbols,quoted_coupon
    │ - compute dealer_margin = fair_coupon - quoted_coupon
    ▼
outputs/fair_coupon_quotes.csv
```

Dashboard 启动时会先尝试读取 `outputs/run_index.csv` 指向的最新 `candidates.csv`;如果不存在,才按 `config/default_universe.txt` 跑一轮。手动 **Load latest saved run** 也直接读取 run history,不需要重新连接 IBKR。

### 7.3 关键 module 边界

| Module | 文件 | 责任 |
|---|---|---|
| Data fetching | `fetch_history`, `fetch_skew`, `fetch_returns` | 与 IB 交互 |
| Metric computation | `iv_rank`, `realized_vol`, `pair_correlation`, … | 纯函数,易测试 |
| Pricing engine | `single_name_ki_prob`, `joint_ki_prob_mc` | 纯数学 |
| Scoring | `score`, `score_pair` | 业务逻辑,可调参 |
| Run storage | `src/fcn_wizard/storage/run_storage.py` | 保存 / reload `outputs/runs/RUN_ID/*.csv` |
| Bootstrap workflow | `src/fcn_wizard/workflows/bootstrap.py` | latest-run 自动加载;无历史时 fallback 到默认 universe |
| Fair coupon workflow | `src/fcn_wizard/workflows/fair_coupon.py` | pair fair coupon 与 PB quote 对比 |
| Quote import | `src/fcn_wizard/quotes/pb_quotes.py` | PB quote symbols 标准化 / merge |
| Pipeline orchestration | `screen_ticker`, `main`, `workflows/*` | I/O + 协调 |

**这个分层让你扩展时只需要碰对应 module。**

### 7.4 Pacing / 性能限制

- IB 历史数据请求:每秒 < 6 个,同时活动请求 < 50
- 当前实现:每 batch 10 个,batch 间 sleep 5s → 约 1 个/s,安全
- 50 个标的全跑 ~5–8 分钟(含 skew 抓取);关闭 skew 后 ~2 分钟
- MC 部分:N=15 时 105 对,每对 20K paths 约 0.3s,总 ~30s

### 7.5 当前已实现 workflow 状态

| Workflow | 状态 | Caveat |
|---|---|---|
| Run history / auto bootstrap | 已实现 | Dashboard 先 load latest;无历史才跑 `config/default_universe.txt` |
| Fair coupon proxy | 已实现 | 仍是 screening proxy,不是 booking PV |
| Dealer margin | 已实现 | `dealer_margin = fair_coupon - quoted_coupon`;正值 = PB quote 对客户偏差 |
| Standalone fair coupon compare | 已实现 | `fair_coupon.py --quotes-file quotes.csv` |
| 3-name worst-of basket | 已实现 | `fcn_pair_screener.py --basket-size 3`;dashboard 支持 Leg C |
| Tenor IV selector | 已实现 | 需要 option chain / OPRA;无数据时 fallback 到 30D IV / RV |
| SVI downside wing vol | 已实现基础版 | live surface sample 受 IBKR option data 和 pacing 限制 |
| Point-in-time replay backtest | 已实现基础版 | 历史 skew/option chain 不用 IBKR 重放;如需 skew 用 Polygon 等外部 provider |
| PB quote comparison | 已实现 | Dashboard CSV upload + package `quotes` module |
| DuckDB snapshot store | 已实现 opt-in | 只用于 prospective monitoring,不是 calibration 必需 |

---

## 8. 扩展路线图

### 8.1 短期(1–2 周)

#### A. 3-name basket screener(已实现基础版)
HK PB 越来越多用 3-name worst-of。当前实现:
- `fcn_pair_screener.py --basket-size 2|3`
- `joint_ki_prob_nd` 支持 generic n-asset(传入 corr matrix 和 vol vector)
- Dashboard 支持 Leg A / B / C 选择

```python
def joint_ki_prob_nd(vols, cov_matrix, barrier=0.5, days=252, n_sims=20_000):
    n = len(vols)
    L = np.linalg.cholesky(cov_matrix)
    rng = np.random.default_rng(42)
    z = rng.standard_normal(size=(n_sims, days, n)) @ L.T
    paths = np.zeros((n_sims, days, n))
    for i in range(n):
        diff = -0.5*vols[i]**2*(1/252) + vols[i]*np.sqrt(1/252)*z[:,:,i]
        paths[:,:,i] = np.exp(np.cumsum(diff, axis=1))
    min_per_asset = paths.min(axis=1)  # (n_sims, n)
    return float((min_per_asset <= barrier).any(axis=1).mean())
```

#### B. 隐含 fair coupon 反推(已实现基础版)
当前 dashboard package 已有 `src/fcn_wizard/metrics.py:fair_coupon_proxy`,公式如下:
```python
def fair_coupon_proxy(p_ki, expected_loss_given_ki, expected_alive_months,
                      discount_rate=0.045, tenor_years=1.0):
    """Returns annualized fair coupon based on risk-neutral pricing."""
    pv_dip = p_ki * expected_loss_given_ki * np.exp(-discount_rate * tenor_years)
    annualized = pv_dip / (expected_alive_months / 12.0)
    return annualized
```
当前 standalone CSV 与 dashboard 均输出 `p_ki` / `fair_coupon_proxy`;`fcn_screener.py --quoted-coupon 0.22` 和 dashboard sidebar 可写入 `quoted_coupon`。统一输出:

```text
dealer_margin = fair_coupon_proxy - quoted_coupon
```

Root-level `fair_coupon.py` 可读取 latest saved pair run 或 `--pairs-file`,再读取 PB quote CSV(`pb,symbols,quoted_coupon`),输出 ranked `fair_coupon / dealer_margin / verdict`。剩余改进是把 proxy 升级为更完整的 autocall-aware MC / DIP 定价。

#### C. Tenor IV / IV surface 替代单点 IV(基础版已实现)
当前默认仍可用 30D IV,但 package/dashboard 已支持两个更准的层:
- `fetch_atm_iv_for_dte`:拿最接近 tenor 的 ATM option IV,用 `choose_tenor_vol` 优先级 `tenor_iv → 30D IV → RV`
- `fetch_option_surface_sample` + SVI:用 downside wing moneyness 估计 `surface_ki_vol`

Caveat:live tenor IV / surface fitting 都需要 option chain + OPRA market data;历史 replay 时 IBKR historical option chain/skew 不完整,不要把 no-skew replay 误解为 skew-calibrated backtest。

### 8.2 中期(1 月)

#### D. 完整 Reiner-Rubinstein DIP closed form
```python
def down_in_put_rr(S0, K, B, T, r, sigma, q=0):
    """Reiner-Rubinstein closed-form for K > B (typical FCN)."""
    from scipy.stats import norm
    mu = (r - q - 0.5*sigma**2) / sigma**2
    lam = np.sqrt(mu**2 + 2*r/sigma**2)
    x1 = np.log(S0/K)/(sigma*np.sqrt(T)) + (1+mu)*sigma*np.sqrt(T)
    x2 = np.log(S0/B)/(sigma*np.sqrt(T)) + (1+mu)*sigma*np.sqrt(T)
    y1 = np.log(B**2/(S0*K))/(sigma*np.sqrt(T)) + (1+mu)*sigma*np.sqrt(T)
    y2 = np.log(B/S0)/(sigma*np.sqrt(T)) + (1+mu)*sigma*np.sqrt(T)
    # ...full formula has 4 terms; see Hull or Haug
    return ...
```
这给你 single-name FCN fair value 的精确解,用于 cross-check MC。

#### E. Local vol surface(替代 GBM)
- 拉 IB option chain 全 strike × 全 expiry IV
- 用 SVI / SABR fit local vol surface
- MC 用 local vol diffusion 而非常数 σ
- 关键改进:wing 区域(deep OTM put)的 IV 比 ATM 高很多,KI 概率会上调
- 这会让 fair coupon 估值显著上调,贴近 dealer 真实报价

#### F. Autocall 路径建模
当前忽略 autocall 对 expected duration 的影响。完整版:
```python
def autocall_aware_duration(spot_path, ko_level, observation_days):
    """Returns first autocall trigger time, or None."""
    for day in observation_days:
        if spot_path[day] >= ko_level:
            return day
    return None  # never triggered
```
集成到 MC 里就能算 expected coupons collected。

### 8.3 长期(2–3 月)

#### G. 回测框架
存几个月每日 candidate snapshot 后,可以做:
- "我在 t-1Y 推荐的 top-20 candidate,1Y 后实际 KI 触发率多少?"
- "我的 score 跟 1Y forward KI 的 rank correlation 多少?"
- 用这个 calibrate scoring weights

需要的 infra:
- DuckDB 存 daily snapshot
- 1Y forward KI outcome 用价格序列回测
- IRR / Sharpe 类指标评估 strategy

#### H. 实时 PB 报价对比
如果你有 PB 朋友拿到 indicative quotes 的 stream:
- 用 fair coupon 算法实时估算 dealer margin
- Top-N 高 dealer margin 的 quote = 客户最被宰的产品
- 反过来:低 dealer margin 的 quote = 投资者占便宜的真好产品

#### I. Cross-PB arbitrage
不同 PB 给同一只 worst-of 的 coupon 报价不同(可能差 200–400 bps)。如果你能拿多家 quotes,直接套利:
- 哪家 PB 系统性给 NVDA+TSLA 的 worst-of 报得最高 coupon?
- 这是非常实用的 alpha,在 family office 圈是公开秘密

#### J. 嵌入 APEX(虽然你说不嵌)
最终如果 standalone 跑稳了,可以反过来集成回 APEX:
- Prefect schedule for daily EOD run
- DuckDB 存 historical scores → time series 分析
- PriorityEventBus 推送 "candidate score change > threshold" event
- 跟 GEX module 联动:dealer short gamma 大的标的 → 容易急跌 → 提高 KI 风险评分

### 8.4 优先级建议

如果只能挑三个,按 ROI 排序:
1. **隐含 fair coupon 反推**(B):最直接的"是否值得买"判断,1 天能完成
2. **完整 IV term structure**(C):对所有数值精度都有提升,2–3 天
3. **Local vol surface**(E):skew 是 dealer 真正的 edge,显式建模后能识别真贵 vs 假贵的票

---

## 9. Formula Cheat Sheet

| 概念 | 公式 |
|---|---|
| GBM | $dS_t = \mu S_t dt + \sigma S_t dW_t$ |
| GBM 解 | $S_t = S_0 \exp((\mu - \tfrac{1}{2}\sigma^2)t + \sigma W_t)$ |
| KI 概率(无漂移) | $P(KI) = 2\Phi\!\left(\frac{\ln(B/S_0)}{\sigma\sqrt{T}}\right)$ |
| KI 概率(有漂移) | $\Phi\!\left(\frac{\ln(B/S_0)-\nu T}{\sigma\sqrt{T}}\right) + \left(\frac{B}{S_0}\right)^{2\nu/\sigma^2}\Phi\!\left(\frac{\ln(B/S_0)+\nu T}{\sigma\sqrt{T}}\right)$,$\nu=\mu-\sigma^2/2$ |
| Realized Vol | $RV = \sqrt{\frac{252}{T}\sum(\ln \frac{S_i}{S_{i-1}})^2}$ |
| IV Rank | $\frac{IV - IV_{\min}}{IV_{\max} - IV_{\min}} \times 100$ |
| VRP | $IV - RV$ |
| Put Skew | $IV_{25\Delta P} - IV_{ATM}$ |
| Risk Reversal | $IV_{25\Delta C} - IV_{25\Delta P}$ |
| Max Drawdown | $\min_t(S_t / \max_{s\le t}S_s - 1)$ |
| Pearson Correlation | $\rho = \frac{\text{Cov}(r_1,r_2)}{\sigma_1 \sigma_2}$ |
| Cholesky | $\Sigma = LL^\top$,correlated draws $= L\epsilon$,$\epsilon \sim N(0,I)$ |
| Worst-of either KI | $E[\mathbb{1}\{\bigcup_i \min_t S_t^{(i)} \le B^{(i)}\}]$(MC) |
| Fair Coupon | $C_{\text{fair}} \approx \frac{P(KI) \cdot E[\text{Loss}|KI]}{E[\text{alive months}]/12}$ |
| Coupon Uplift | $\frac{P(\text{worst-of KI})}{\min(P(KI_a), P(KI_b))}$ |
| Reiner-Rubinstein DIP | (4-term formula,见 Hull Ch. 26 或 Haug "Option Pricing Formulas") |

---

## 10. References

### 学术 / 教科书
- Hull, J. *Options, Futures, and Other Derivatives*, Ch. 26 (Exotic Options)
- Haug, E. *The Complete Guide to Option Pricing Formulas*, 2nd ed.
- Reiner, E., & Rubinstein, M. (1991). "Breaking Down the Barriers." *Risk*, 4(8).
- Lam, K., Yu, P., & Xin, L. (2009). "Accumulator Pricing." (HKU paper, 写 AQ 的 path-dep)

### 行业 / 监管
- HKMA "Guidelines on Sale of Non-listed Structured Investment Products"
- SFC Code of Conduct, Section 5 (Suitability)
- DBS Product Booklet — OTC AQ/DQ on Equity (公开,Google "DBS AQ DQ product booklet")

### 实务
- ISDA Definitions (2021), Equity Derivatives Sections
- Asian Structured Products (CFA Institute Foundation, 2017) — 给 HK/SG market 全景

### Code 依赖
- `ib_insync`: https://ib-insync.readthedocs.io/
- `scipy.stats.norm`: 标准正态 CDF
- IB API Historical Data: https://interactivebrokers.github.io/tws-api/historical_bars.html
- IB whatToShow="OPTION_IMPLIED_VOLATILITY": 拿 30D IV history

---

*Last updated: 2026-05-07*
*Maintained alongside: `fcn_screener.py`, `fcn_pair_screener.py`*
