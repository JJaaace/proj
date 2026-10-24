# Integration file inventory

Changes relative to `origin/main` at `db8ee02`, including merged contributions.
`A` added, `M` modified, `D` deleted, `R` moved (similarity shown by Git).
All original teammate tests remain. Duplicate root analytics from Teja were also
removed after byte comparison; those copies were never in the integration base
and therefore are not separate deletions in this base-relative list.

| Change | File | Reason |
|---|---|---|
| `A` | `AEP_Project/storm-assistant/INTEGRATION_REPORT.md` | Integration provenance, results, review instructions, and per-file inventory. |
| `M` | `AEP_Project/storm-assistant/README.md` | Consolidated application documentation or preserved shared project asset. |
| `A` | `AEP_Project/storm-assistant/analytics/__init__.py` | Actual Person 2 analytics merged; no predictive/geospatial algorithms replaced. |
| `A` | `AEP_Project/storm-assistant/analytics/geospatial/__init__.py` | Actual Person 2 analytics merged; no predictive/geospatial algorithms replaced. |
| `A` | `AEP_Project/storm-assistant/analytics/geospatial/clustering.py` | Actual Person 2 analytics merged; no predictive/geospatial algorithms replaced. |
| `A` | `AEP_Project/storm-assistant/analytics/geospatial/hazards.py` | Actual Person 2 analytics merged; no predictive/geospatial algorithms replaced. |
| `A` | `AEP_Project/storm-assistant/analytics/geospatial/storm_overlay.py` | Actual Person 2 analytics merged; no predictive/geospatial algorithms replaced. |
| `R100` | `storm-assistant/analytics/network/__init__.py -> AEP_Project/storm-assistant/analytics/network/__init__.py` | Move the original implementation into the canonical application; source history retained. |
| `R100` | `storm-assistant/analytics/network/demo.py -> AEP_Project/storm-assistant/analytics/network/demo.py` | Move the original implementation into the canonical application; source history retained. |
| `R100` | `storm-assistant/analytics/network/graph_builder.py -> AEP_Project/storm-assistant/analytics/network/graph_builder.py` | Move the original implementation into the canonical application; source history retained. |
| `R100` | `storm-assistant/analytics/network/root_cause.py -> AEP_Project/storm-assistant/analytics/network/root_cause.py` | Move the original implementation into the canonical application; source history retained. |
| `R100` | `storm-assistant/analytics/network/tracing.py -> AEP_Project/storm-assistant/analytics/network/tracing.py` | Move the original implementation into the canonical application; source history retained. |
| `A` | `AEP_Project/storm-assistant/analytics/predictive/__init__.py` | Actual Person 2 analytics merged; no predictive/geospatial algorithms replaced. |
| `A` | `AEP_Project/storm-assistant/analytics/predictive/etr.py` | Actual Person 2 analytics merged; no predictive/geospatial algorithms replaced. |
| `A` | `AEP_Project/storm-assistant/analytics/predictive/features.py` | Actual Person 2 analytics merged; no predictive/geospatial algorithms replaced. |
| `A` | `AEP_Project/storm-assistant/analytics/predictive/models/outage_risk_v1.json` | Actual Person 2 analytics merged; no predictive/geospatial algorithms replaced. |
| `A` | `AEP_Project/storm-assistant/analytics/predictive/outage_risk.py` | Actual Person 2 analytics merged; no predictive/geospatial algorithms replaced. |
| `A` | `AEP_Project/storm-assistant/analytics/predictive/train.py` | Actual Person 2 analytics merged; no predictive/geospatial algorithms replaced. |
| `A` | `AEP_Project/storm-assistant/channels/__init__.py` | Actual Person 4 pipeline, templates, fixed safety, tests; compatible clock/privacy fixes where documented. |
| `A` | `AEP_Project/storm-assistant/channels/sms/__init__.py` | Actual Person 4 pipeline, templates, fixed safety, tests; compatible clock/privacy fixes where documented. |
| `A` | `AEP_Project/storm-assistant/channels/sms/consent.py` | Actual Person 4 pipeline, templates, fixed safety, tests; compatible clock/privacy fixes where documented. |
| `A` | `AEP_Project/storm-assistant/channels/sms/provider.py` | Actual Person 4 pipeline, templates, fixed safety, tests; compatible clock/privacy fixes where documented. |
| `R100` | `storm-assistant/data/__init__.py -> AEP_Project/storm-assistant/data/__init__.py` | Move the original implementation into the canonical application; source history retained. |
| `R100` | `storm-assistant/data/connectors/__init__.py -> AEP_Project/storm-assistant/data/connectors/__init__.py` | Move the original implementation into the canonical application; source history retained. |
| `R100` | `storm-assistant/data/connectors/sample_data.py -> AEP_Project/storm-assistant/data/connectors/sample_data.py` | Move the original implementation into the canonical application; source history retained. |
| `R084` | `storm-assistant/data/sample/customers.json -> AEP_Project/storm-assistant/data/sample/customers.json` | Move the original implementation into the canonical application; source history retained. |
| `R100` | `storm-assistant/data/sample/feeders.json -> AEP_Project/storm-assistant/data/sample/feeders.json` | Move the original implementation into the canonical application; source history retained. |
| `R100` | `storm-assistant/data/sample/storm.json -> AEP_Project/storm-assistant/data/sample/storm.json` | Move the original implementation into the canonical application; source history retained. |
| `R100` | `storm-assistant/data/sample/storm_timeline.json -> AEP_Project/storm-assistant/data/sample/storm_timeline.json` | Move the original implementation into the canonical application; source history retained. |
| `R100` | `storm-assistant/data/sample/substations.json -> AEP_Project/storm-assistant/data/sample/substations.json` | Move the original implementation into the canonical application; source history retained. |
| `R100` | `storm-assistant/data/sample/transformers.json -> AEP_Project/storm-assistant/data/sample/transformers.json` | Move the original implementation into the canonical application; source history retained. |
| `R100` | `storm-assistant/data/schemas/__init__.py -> AEP_Project/storm-assistant/data/schemas/__init__.py` | Move the original implementation into the canonical application; source history retained. |
| `R100` | `storm-assistant/data/schemas/models.py -> AEP_Project/storm-assistant/data/schemas/models.py` | Move the original implementation into the canonical application; source history retained. |
| `A` | `AEP_Project/storm-assistant/docs/SPEC_extracted.txt` | Consolidated application documentation or preserved shared project asset. |
| `A` | `AEP_Project/storm-assistant/docs/message_catalog.md` | Consolidated application documentation or preserved shared project asset. |
| `A` | `AEP_Project/storm-assistant/messaging/SPEC_PERSON4.md` | Actual Person 4 pipeline, templates, fixed safety, tests; compatible clock/privacy fixes where documented. |
| `A` | `AEP_Project/storm-assistant/messaging/__init__.py` | Actual Person 4 pipeline, templates, fixed safety, tests; compatible clock/privacy fixes where documented. |
| `A` | `AEP_Project/storm-assistant/messaging/composer.py` | Actual Person 4 pipeline, templates, fixed safety, tests; compatible clock/privacy fixes where documented. |
| `A` | `AEP_Project/storm-assistant/messaging/guardrails.py` | Actual Person 4 pipeline, templates, fixed safety, tests; compatible clock/privacy fixes where documented. |
| `A` | `AEP_Project/storm-assistant/messaging/safety/README.md` | Actual Person 4 pipeline, templates, fixed safety, tests; compatible clock/privacy fixes where documented. |
| `A` | `AEP_Project/storm-assistant/messaging/safety/downed_wires.txt` | Actual Person 4 pipeline, templates, fixed safety, tests; compatible clock/privacy fixes where documented. |
| `A` | `AEP_Project/storm-assistant/messaging/safety/gas_smell.txt` | Actual Person 4 pipeline, templates, fixed safety, tests; compatible clock/privacy fixes where documented. |
| `A` | `AEP_Project/storm-assistant/messaging/safety/immediate_danger.txt` | Actual Person 4 pipeline, templates, fixed safety, tests; compatible clock/privacy fixes where documented. |
| `A` | `AEP_Project/storm-assistant/messaging/safety/medical.txt` | Actual Person 4 pipeline, templates, fixed safety, tests; compatible clock/privacy fixes where documented. |
| `A` | `AEP_Project/storm-assistant/messaging/templates/crew_assigned.txt` | Actual Person 4 pipeline, templates, fixed safety, tests; compatible clock/privacy fixes where documented. |
| `A` | `AEP_Project/storm-assistant/messaging/templates/etr_update.txt` | Actual Person 4 pipeline, templates, fixed safety, tests; compatible clock/privacy fixes where documented. |
| `A` | `AEP_Project/storm-assistant/messaging/templates/outage_confirmed.txt` | Actual Person 4 pipeline, templates, fixed safety, tests; compatible clock/privacy fixes where documented. |
| `A` | `AEP_Project/storm-assistant/messaging/templates/pre_storm.txt` | Actual Person 4 pipeline, templates, fixed safety, tests; compatible clock/privacy fixes where documented. |
| `A` | `AEP_Project/storm-assistant/messaging/templates/restored.txt` | Actual Person 4 pipeline, templates, fixed safety, tests; compatible clock/privacy fixes where documented. |
| `A` | `AEP_Project/storm-assistant/messaging/tests/test_messaging.py` | Actual Person 4 pipeline, templates, fixed safety, tests; compatible clock/privacy fixes where documented. |
| `A` | `AEP_Project/storm-assistant/messaging/throttle.py` | Actual Person 4 pipeline, templates, fixed safety, tests; compatible clock/privacy fixes where documented. |
| `A` | `AEP_Project/storm-assistant/requirements-dev.txt` | Retain NetworkX requirement and make pytest development setup reproducible. |
| `R100` | `storm-assistant/requirements.txt -> AEP_Project/storm-assistant/requirements.txt` | Move the original implementation into the canonical application; source history retained. |
| `A` | `AEP_Project/storm-assistant/services/__init__.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/services/context/__init__.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/services/context/contracts.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/services/context/lifecycle.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/services/context/snapshot.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/services/events/__init__.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/services/events/audit.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/services/events/triggers.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/services/forecasting/__init__.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/tests/__init__.py` | Consolidated application documentation or preserved shared project asset. |
| `A` | `AEP_Project/storm-assistant/tests/analytics/conftest.py` | Retain original Person 2 test cases; isolate calibration inputs and training artifacts. |
| `A` | `AEP_Project/storm-assistant/tests/analytics/test_geospatial.py` | Retain original Person 2 test cases; isolate calibration inputs and training artifacts. |
| `A` | `AEP_Project/storm-assistant/tests/analytics/test_person2_legacy.py` | Retain original Person 2 test cases; isolate calibration inputs and training artifacts. |
| `A` | `AEP_Project/storm-assistant/tests/analytics/test_person2_models.py` | Retain original Person 2 test cases; isolate calibration inputs and training artifacts. |
| `A` | `AEP_Project/storm-assistant/tests/analytics/test_predictive.py` | Retain original Person 2 test cases; isolate calibration inputs and training artifacts. |
| `A` | `AEP_Project/storm-assistant/tests/storm_replay/IMPROVEMENT_REPORT.md` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/tests/storm_replay/README.md` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/tests/storm_replay/__init__.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/tests/storm_replay/conftest.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/tests/storm_replay/demo.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/tests/storm_replay/integration.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/tests/storm_replay/presentation.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/tests/storm_replay/replay.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/tests/storm_replay/test_audit.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/tests/storm_replay/test_full_system.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/tests/storm_replay/test_integration.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/tests/storm_replay/test_lifecycle.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/tests/storm_replay/test_person2_branch.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/tests/storm_replay/test_regressions.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/tests/storm_replay/test_replay.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `A` | `AEP_Project/storm-assistant/tests/storm_replay/test_triggers.py` | Actual Person 3 orchestration, regressions, audit; real-module wiring and deferred-result integration. |
| `M` | `README.md` | Consolidated application documentation or preserved shared project asset. |
| `A` | `pytest.ini` | Canonical application import path and collision-free collection of every original suite. |
| `D` | `storm-assistant/.env.example` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/README.md` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/apps/api/src/auth/.gitkeep` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/apps/api/src/domain/.gitkeep` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/apps/api/src/integrations/gis.py` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/apps/api/src/integrations/grid_network.py` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/apps/api/src/integrations/outage_system.py` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/apps/api/src/integrations/weather.py` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/apps/api/src/main.py` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/apps/api/src/routes/.gitkeep` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/apps/api/src/services/customer_status.py` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/apps/api/src/services/notification_service.py` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/apps/api/src/services/outage_service.py` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/apps/api/tests/.gitkeep` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/apps/web/.gitkeep` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/data/examples/.gitkeep` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/data/schemas/.gitkeep` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/docs/architecture.md` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/docs/customer-messaging.md` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/docs/data-sources.md` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/infra/.gitkeep` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/packages/contracts/.gitkeep` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/services/forecasting/.gitkeep` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/tests/fixtures/.gitkeep` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `D` | `storm-assistant/tests/integration/.gitkeep` | Remove byte-identical old scaffold; canonical counterpart is retained. |
| `A` | `AEP_Project/storm-assistant/INTEGRATION_FILES.md` | This complete per-file inventory. |
