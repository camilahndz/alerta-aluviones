"""Parche de compatibilidad entre pysheds 0.5 y numpy >= 2.

pysheds 0.5 todavia llama a `np.in1d`, un alias que numpy elimino en la version
2.0. El reemplazo oficial es `np.isin`, que hace exactamente lo mismo; la unica
diferencia historica entre ambos era la forma del resultado, y en las nueve
llamadas de pysheds la entrada ya viene aplanada con `.ravel()`, asi que el
comportamiento es identico.

Sin esto, cualquier llamada a accumulation(), catchment() o similares revienta
con AttributeError.

Importar ESTE modulo antes que pysheds:

    import compat_pysheds  # noqa: F401
    from pysheds.grid import Grid

Cuando pysheds publique una version compatible con numpy 2, este archivo se
puede borrar junto con sus imports.
"""

import numpy as np

if not hasattr(np, "in1d"):
    np.in1d = np.isin
