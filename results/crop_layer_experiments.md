# Crop and layer experiment results

Solver: `fast_marching`; delta: 0.5°; dt: 40 years; W: True; theta bounds: [-5, 5]. Initial sweep: 3 points per coefficient.
Theta values are listed as intercept, then coefficients for the named layers. Values come from projected gradient descent after a coarse theta sweep; a nested simpler fit is kept if it scores better. A global optimum is not guaranteed.

| Crop | Layers | Best theta (fit) | Best squared error (years²) |
| --- | --- | --- | ---: |
| wheat | average only | -0.6501115839 | 2,603,382.419 |
| wheat | sea | -1.561911448, 4.998749883 | 1,508,944.689 |
| wheat | prec + sea | -1.460623728, 0.235379236, 5 | 1,480,413.147 |
| wheat | tmean + sea | -1.309205192, -0.5444632811, 4.999885948 | 1,461,435.049 |
| wheat | csi + sea | -1.558355876, 0.004002259349, 4.9989073 | 1,508,888.719 |
| wheat | hydro + sea | -1.548788144, -0.106184829, 5 | 1,497,836.176 |
| rice | average only | 0.5653372907 | 3,700,183.827 |
| rice | sea | 3.263617264, -4.611381671 | 3,360,588.026 |
| rice | prec + sea | -0.21345671, 2.402015881, -4.352857425 | 1,752,528.659 |
| rice | tmean + sea | -1.166972945, 4.681769843, -4.601132032 | 1,667,686.675 |
| rice | csi + sea | 2.721484692, -1.714993323, -4.083561318 | 1,950,037.173 |
| rice | hydro + sea | 0.5423765641, 5, -1.905411738 | 2,123,258.119 |
| maize | average only | -0.3330720896 | 967,557.745 |
| maize | sea | -0.03424398096, -4.685513964 | 905,460.801 |
| maize | prec + sea | -0.01219739507, -4.957227293, 0.3133650621 | 882,052.420 |
| maize | tmean + sea | 0.0841738317, -0.2065442371, -4.777025657 | 870,954.352 |
| maize | csi + sea | -0.08051262406, 0.006049462469, -4.634828394 | 889,530.050 |
| maize | hydro + sea | 0.1056948041, 5, -4.760756222 | 729,672.740 |
