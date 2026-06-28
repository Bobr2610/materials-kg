[0m
> build · mimo-auto
[0m
[0m→ [0mSkill "materials-knowledge-graph"
[0m⚙ [0mtask Task created: T1
[0m⚙ [0mtask Task T1: in_progress
[0m✱ [0mGlob "kg_engine/**/*.py"[90m 100 matches[0m
[0m→ [0mRead kg_engine\graph\__init__.py
[0m→ [0mRead kg_engine\services\materials_kg.py
[0m→ [0mRead kg_engine\scripts\run_materials_api.py
[0m✱ [0mGlob "kg_engine/api/**/*.py"[90m 7 matches[0m
[0m→ [0mRead kg_engine\api\materials_core.py
[0m→ [0mRead kg_engine\tests\test_materials_api_smoke.py
[0m✱ [0mGlob "kg_engine/domain/**/*.py"[90m 3 matches[0m
[0m✱ [0mGlob "kg_engine/repositories/**/*.py"[90m 5 matches[0m
[0m→ [0mRead kg_engine\domain\models.py
[0m→ [0mRead kg_engine\repositories\protocols.py
[0m→ [0mRead kg_engine\repositories\memory.py
[0m→ [0mRead kg_engine\repositories\factory.py
[0m→ [0mRead kg_engine\config\settings.py
[0m→ [0mRead kg_engine\tests\test_materials_kg_core.py
[0m→ [0mRead kg_engine\repositories\postgres.py
[0m
[0m$ [0m.venv\Scripts\Activate.ps1; python -m pytest kg_engine/tests/test_materials_api_smoke.py -v
.venv\Scripts\Activate.ps1 : The module '.venv' could not be loaded. For more information, run 'Import-Module .venv'.
At line:1 char:1
+ .venv\Scripts\Activate.ps1; python -m pytest kg_engine/tests/test_mat ...
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : ObjectNotFound: (.venv\Scripts\Activate.ps1:String) [], CommandNotFoundException
    + FullyQualifiedErrorId : CouldNotAutoLoadModule
 
============================= test session starts =============================
platform win32 -- Python 3.11.5, pytest-9.0.2, pluggy-1.6.0 -- C:\Program Files\Python311\python.exe
cachedir: .pytest_cache
rootdir: C:\MAI\Nornicel\Code\materials-kg
configfile: pyproject.toml
plugins: anyio-4.11.0, hydra-core-1.3.2, base-url-2.1.0, playwright-0.7.2
collecting ... collected 1 item
System.Management.Automation.RemoteException
kg_engine/tests/test_materials_api_smoke.py::test_materials_api_health_and_ingest_query_flow PASSED [100%]
System.Management.Automation.RemoteException
============================== 1 passed in 0.99s ==============================
[0m
