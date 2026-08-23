# Manuscript-aligned reference implementation

This package is an executable reconstruction of the tactical method specified
in `../a2rl_paper.tex`.  It implements:

- the reported ten-dimensional action bounds, affine tanh-space mapping, and
  safety projection;
- callback-based Stackelberg leader selection, follower iterative best
  responses, a local response neighborhood, and the robust game-value target;
- the five-mode hysteretic FSM, readiness/abort gates, and persistent pass-side
  lock;
- opponent-footprint projection, side-specific corridor exclusion, far-field
  width/bias blending, the 3 m minimum-width guard, and temporal filtering;
- a 51-input/10-output PyTorch TQC actor, two 25-atom critics, the 46-atom
  truncated target, quantile-Huber regression, weighted IBR-prior loss, and an
  auxiliary robust game-value head;
- the dimensionless tire-force-envelope utilization and the state-dependent
  action-projection callback used before actor and target-critic evaluation.

The implementation is reconstructed from the author-confirmed manuscript and
is supplied so that the equations have a runnable, inspectable counterpart. It
is not represented as a byte-identical copy of the historical training source
used for the HIL campaign. In particular, scenario-specific utilities,
follower dynamics, IBR budgets, Shadow/Defend shaping scales, fade/blend
parameters, loss weights, and numerical gate constants not printed in the
manuscript are explicit callbacks or required configuration inputs rather than
guessed deployment values. The numbers in the unit tests are test fixtures,
not claims about the historical configuration.

The prior and game-value head are training-time components. The
`inference_state_dict()` method intentionally exports only actor and critics,
showing how a deployment archive may retain a standard TQC inference structure
without the auxiliary game head.  The deterministic tire-force projector has no
trainable state and is therefore configured alongside the deployed actor rather
than serialized in that state dictionary.  Target critics must receive the
action returned by `constrained_policy_action()`.

Run the dependency-light tests from `CEP/`:

```bash
python3 -m unittest discover -s reference_implementation/tests -p 'test_reference.py'
```

Run the PyTorch loss test with an environment that provides PyTorch:

```bash
python -m unittest discover -s reference_implementation/tests -p 'test_tqc.py'
```
