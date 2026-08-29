# CEP论文三处核心修改：最小侵入版

## 总体边界

- 不修改摘要、贡献、结论和建模章节。
- 不新增小节，不展开观测维度、训练超参数或执行器细节。
- 正文只加入三个核心数学对象；Algorithm 1同步三行。

---

## 修改一：用联合预览算子闭合response-set teacher

### 正文位置

第3.1节 `Robust Stackelberg response-set supervision` 中，找到：

```latex
Let $\mathcal A_i^G(\bm o)$ denote the resulting bank for role $i$.
For each ego--opponent pair, the two role-swapped previews are interpolated
onto their common elapsed-time horizon before the role-relative utility is
evaluated:
```

删除并替换为：

```latex
Let
\(
\bm s_t^G=(\widetilde{\bm o}_t,\bm\chi_t^G)
\)
denote the teacher state, where $\bm\chi_t^G$ collects the publisher,
executor, and one-step reward memory carried between tactical updates, and
let $\mathcal A_i^G(\bm s_t^G)$ denote the candidate bank for role $i$.
Each candidate pair induces the coupled executable preview
\begin{equation}
(\mathcal R_e,\mathcal R_o)=
\mathscr P_{N_{\rm sta}}\!\left(
\bm s_t^G;\bm a_e^{\rm F},\bm a_o^{\rm F}\right),
\label{eq:coupled_game_preview}
\end{equation}
where $\mathscr P_{N_{\rm sta}}$ recursively applies the stateful publisher
in Algorithm~\ref{alg:tactical_corridor} and the common execution stack.
The candidate pair remains fixed over the preview while both vehicle and
hybrid states evolve jointly; both utilities use the corresponding
role-relative features of this preview.
```

### Algorithm 1：替换第一行

删除：

```latex
\STATE discard duplicate or infeasible candidates; build paired role-swapped
previews on the common elapsed-time horizon
```

替换为：

```latex
\STATE discard duplicate or infeasible candidates; generate the coupled
preview~\eqref{eq:coupled_game_preview} for each candidate pair
```

---

## 修改二：归一化效用尺度，并把teacher label并入数据集定义

### 1. 替换式 `\eqref{eq:game_utility}` 及其下一句

删除从：

```latex
\begin{equation}
U_i(\bm o,\bm a_e^{\rm F},\bm a_o^{\rm F})=
```

到：

```latex
\ref{app:parameters}.
```

替换为：

```latex
Let
\(
Z_g=\sum_{k=0}^{N_{\rm sta}-1}\gamma_g^k
\)
and
\(
c_w=\sum_{j=1}^{10}[-w_j]_+
\).
The normalized role-relative utility is
\begin{equation}
U_i(\bm s_t^G,\bm a_e^{\rm F},\bm a_o^{\rm F})=
\frac{1}{Z_g\|\bm w\|_1}
\sum_{k=0}^{N_{\rm sta}-1}\gamma_g^k
\left[\bm w^\top\bm\phi_{i,k}(\mathcal R_e,\mathcal R_o)+c_w\right],
\label{eq:game_utility}
\end{equation}
where $\bm\phi_i\in[0,1]^{10}$ contains the role-relative reward features in
\ref{app:parameters}. Hence $U_i\in[0,1]$, and
$\varepsilon_{\rm BR}$ directly specifies the admissible follower-utility gap.
```

### 2. 整体替换式 `\eqref{eq:response_set_teacher}`

```latex
\begin{equation}
\begin{aligned}
U_o^{\max}(\bm s_t^G,\bm a_e^{\rm F})
&=\max_{\bm a_o^{\rm F}\in\mathcal A_o^G(\bm s_t^G)}
U_o(\bm s_t^G,\bm a_e^{\rm F},\bm a_o^{\rm F}),\\
\mathfrak R_o^\varepsilon(\bm s_t^G,\bm a_e^{\rm F})
&=\left\{\bm a_o^{\rm F}\in\mathcal A_o^G(\bm s_t^G):
U_o^{\max}(\bm s_t^G,\bm a_e^{\rm F})
-U_o(\bm s_t^G,\bm a_e^{\rm F},\bm a_o^{\rm F})
\le\varepsilon_{\rm BR}\right\},\\
\mathcal V_g(\bm s_t^G,\bm a_e^{\rm F})
&=\min_{\bm a_o^{\rm F}\in
\mathfrak R_o^\varepsilon(\bm s_t^G,\bm a_e^{\rm F})}
U_e(\bm s_t^G,\bm a_e^{\rm F},\bm a_o^{\rm F}),\\
\bm a_{\rm th}^{\star}(\bm s_t^G)
&\in\argmax_{\bm a_e^{\rm F}\in\mathcal A_e^G(\bm s_t^G)}
\mathcal V_g(\bm s_t^G,\bm a_e^{\rm F}),\\
\mathcal D_g
&=\left\{(\widetilde{\bm o}_n,\bm a_{g,n}^{\rm F},v_{g,n},
\bm a_{{\rm th},n}^{\star}):
v_{g,n}=\mathcal V_g(\bm s_n^G,\bm a_{g,n}^{\rm F})\right\}.
\end{aligned}
\label{eq:response_set_teacher}
\end{equation}
Here $\varepsilon_{\rm BR}=0.05$ retains responses within $0.05$ of the best
candidate on the normalized utility scale.
```

### 3. TQC段落：同步teacher tuple

将：

```latex
For matched
$(\widetilde{\bm o}_g,\bm a_g^{\rm F},v_g)\sim\mathcal D_g$
```

替换为：

```latex
For matched
$(\widetilde{\bm o}_g,\bm a_g^{\rm F},v_g,
\bm a_{\rm th}^{\star})\sim\mathcal D_g$
```

将actor先验项中的：

```latex
\mathbb E_{\widetilde{\bm o}\sim\mathcal D_g}
```

替换为：

```latex
\mathbb E_{\mathcal D_g}
```

### Algorithm 1：替换第二行

删除：

```latex
\STATE store every matched $(\widetilde{\bm o},\bm a^{\rm F},v_g)$ in
$\mathcal D_g$ and retain $\bm a_{\rm th}^{\star}$ as the action prior
```

替换为：

```latex
\STATE store every matched
$(\widetilde{\bm o},\bm a^{\rm F},v_g,\bm a_{\rm th}^{\star})$
in $\mathcal D_g$
```

---

## 修改三：将轮胎投影写成独立的动作条件化证书

### 正文位置

第3.1节中，删除从：

```latex
Before publication, the requested corridor and speed cap are aligned ...
```

到：

```latex
fallback.
```

即删除当前轮胎投影的整段文字和式 `\eqref{eq:tire_safe_action}`，替换为：

```latex
Before publication, the requested speed cap is certified against the
speed-dependent tire envelope on the provisional corridor midpoint. For each
trial $v\in\mathcal V_s(V_{\rm cap}^{\rm req})$, define the envelope-unclipped
kinetic-energy template
\begin{equation}
\lambda_k=
\frac{\sum_{j=0}^{k-1}\Delta\ell_j}
{\sum_{j=0}^{N_{\rm sta}-2}\Delta\ell_j},
\qquad
\widehat V_k(v)=
\sqrt{V_e^2+\lambda_k\bigl(v^2-V_e^2\bigr)}.
\label{eq:tire_speed_template}
\end{equation}
Using the midpoint curvature $\widehat\kappa_k$, the induced demand and total
projection are
\begin{equation}
\begin{aligned}
\widehat a_{T,k}(v)
&=\frac{\widehat V_{k+1}^2(v)-\widehat V_k^2(v)}{2\Delta\ell_k}
+\frac{F_{\rm drag}(\widehat V_k(v))}{m},\\
\widehat a_{N,k}(v)
&=\widehat\kappa_k\widehat V_k^2(v),\\
\widehat\rho(v)
&=\max_{0\le k\le N_{\rm sta}-2}\Phi_{\rm tire}\!\left(
\widehat a_{T,k}(v),\widehat a_{N,k}(v),\widehat V_k(v)\right),\\
\mathcal V_{\rm adm}(\bm a)
&=\left\{v\in\mathcal V_s(V_{\rm cap}^{\rm req}):
\widehat\rho(v)\le1\right\},\\
\Pi_{\rm tire}(\bm a;\widetilde{\bm o})
&=\begin{cases}
\bm a[\max\mathcal V_{\rm adm}(\bm a)],
&\mathcal V_{\rm adm}(\bm a)\neq\varnothing,\\
\bm a_{\rm HF}^{\rm F}(\widetilde{\bm o}),
&\mathcal V_{\rm adm}(\bm a)=\varnothing.
\end{cases}
\end{aligned}
\label{eq:tire_safe_action}
\end{equation}
Here $V_e$ is the current ego speed, $\mathcal V_s$ is the uniformly sampled
finite grid from $V_{\min}$ to $V_{\rm cap}^{\rm req}$, and $\bm a[v]$ changes
only the cap component. The total branch $\bm a_{\rm HF}^{\rm F}$ performs the
current-state \textsc{Hold} reconstruction and returns the braking-fallback
contract if its repeated search remains empty.
```

这段只调用建模章节已有的 `\Phi_{\rm tire}`，不修改
`\mathcal A_{\rm tire}(V)` 及其速度相关建模。

### Algorithm 1：替换第三行

删除：

```latex
\STATE run the finite search~\eqref{eq:tire_safe_action}; if empty, rebuild
current-state \textsc{Hold} once and repeat the search; return fallback if it
remains empty
```

替换为：

```latex
\STATE evaluate~\eqref{eq:tire_safe_action}, including its deterministic
current-state \textsc{Hold}/braking branch
```

### 第4节：插入一句

在原文：

```latex
For curvature \(\kappa_{p,k}\), the envelope supplies ...
```

之前插入：

```latex
The forward--backward sweep distributes the certified tactical cap over the
optimized path.
```

---

## 提交前的一致性动作（不写入论文）

- 用归一化式 `\eqref{eq:game_utility}` 生成 `\mathcal D_g`，并保持
  `\varepsilon_{\rm BR}=0.05`。
- teacher、TQC target和在线publication统一调用式
  `\eqref{eq:tire_safe_action}` 的同一总映射。

以上修改不触碰摘要与创新点，也不增加新的实验表格。
