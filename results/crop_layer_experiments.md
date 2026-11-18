# Crop and layer experiment results

Solver: `monte_carlo`; delta: 0.5°; dt: 40 years; W: True; theta bounds: [-5, 5]. Repetitions: 20; seed: 12. Initial sweep: 11 points per coefficient.
Theta values are listed as intercept, then coefficients for the named layers. Values come from SLSQP fitting after a coarse theta sweep; a nested simpler fit is kept if it scores better. A global optimum is not guaranteed.

| Crop | Layers | Best theta (fit) | Best squared error (years²) |
| --- | --- | --- | ---: |
| wheat | average only | -1.198495965 | 2,493,105.700 |
| wheat | sea | -2, 4 | 1,641,647.982 |
| wheat | prec + sea | -0.00501414847, 4.001002832, 3.990974439 | 1,392,569.026 |
| wheat | tmean + sea | -1.6, -1, 5 | 1,525,066.101 |
| wheat | csi + sea | -2, 0, 4 | 1,641,647.982 |
| wheat | hydro + sea | -2, -1, 4 | 1,570,633.379 |
| rice | average only | 0.09944510594 | 3,389,673.776 |
| rice | sea | 0.4037917571, -3.319835181 | 1,881,883.505 |
| rice | prec + sea | -0.3360682887, 1.929751377, -4.02977481 | 1,581,184.230 |
| rice | tmean + sea | -1.60261202, 4.999014444, -5 | 1,460,975.710 |
| rice | csi + sea | 1.2, -1, -4 | 1,735,522.199 |
| rice | hydro + sea | 0.4, 5, -3 | 1,768,818.260 |
| maize | average only | -0.8 | 1,004,060.469 |
| maize | sea | -0.8, -1 | 875,774.783 |
| maize | prec + sea | -0.7809336491, -4.942929687, 1.943224774 | 517,181.995 |
| maize | tmean + sea | 1.200190526, -3.999548707, 5 | 406,834.367 |
| maize | csi + sea | -0.6018523217, -0.08716640951, -0.8372065427 | 745,109.362 |
| maize | hydro + sea | -0.3820562914, 3.814851021, -2.874496701 | 778,618.531 |
