# Provisional taxonomy expansion

## Nodes added

- `structural_analysis`: structural response modeling and evaluation under stated
  loads, combinations, or constraints.
- `structural_design`: selection, sizing, or detailing of structural systems or
  members against stated requirements. It remains distinct from analysis.
- `mechanical_design`: creation or refinement of mechanical parts and assemblies
  through explicit geometry, fit, interference, material, or functional choices.
- `engineering_simulation`: construction, execution, or interpretation of numerical
  or physics-based models for engineered systems.
- `embedded_digital_systems`: digital logic, sensors, firmware, or control behavior
  integrated with embedded hardware.
- `qualitative_research`: systematic collection, coding, comparison, or
  interpretation of nonnumeric research evidence.
- `teaching_instruction`: planning, delivering, adapting, or evaluating instruction
  or tutoring for identified learners.

All seven nodes are provisional, have no named validator or source, and include
supporting evidence, insufficient evidence, aliases, and common false-positive
traps in the taxonomy files.

## Existing nodes reused

- `programming` now covers demonstrated SQL query construction and SQL data analysis.
- `machine_learning` covers demonstrated NLP classifier work; no separate NLP node
  was necessary.
- `networking` and `security` retain distinct packet/traffic and protection/detection
  meanings. Detection engineering reused `security`; no new cybersecurity node was
  added.
- `quantitative_analysis` was clarified rather than split. A numeric result,
  measured impact, structural calculation, or tool name alone is insufficient.

## Nodes considered but rejected

- Tool nodes for ETABS, AutoCAD, SolidWorks, ANSYS, MATLAB, Arduino, Verilog,
  Wireshark, Nessus, PyTorch, and similar products were rejected.
- A combined structural-engineering node was rejected because structural analysis
  and structural design require different evidence.
- Mechanical CAD and finite-element-analysis subnodes were rejected; the evidence
  fits mechanical design or engineering simulation without naming tools as skills.
- Detection engineering, vulnerability assessment, network analysis, NLP, SQL/data
  querying, sensor characterization, and digital control subnodes were rejected in
  favor of existing or newly added broader nodes.
- Technical drafting, cloud deployment, and generic workflow/process design nodes
  were deferred because the suites currently provide too little or overly broad
  evidence for safe definitions.

## Null-ID evidence now resolved

Twenty-eight supported null-ID suggestions were resolved: structural analysis (9),
structural design (2), mechanical design (4), engineering simulation (4), embedded
and digital systems (3), qualitative research (1), teaching/instruction (1),
programming (2), machine learning (1), and security (1).

## Evidence still unmapped

The remaining supported null-ID methods are technical drafting, cloud deployment,
and generic workflow design. They remain visible as reviewable gaps. They were not
forced into mechanical design, distributed systems, programming, or quantitative
analysis.

## False-positive regressions

- All 16 bare-tool semantic cases remain context-only with no competency suggestion.
- ETABS activity may support structural analysis; bare ETABS does not. Comparing
  supplied beam designs does not establish personal structural design.
- Bare SolidWorks and ANSYS do not establish mechanical design or engineering
  simulation.
- Bare Arduino or Verilog does not establish embedded/digital-systems competency.
- Bare Wireshark, Nessus, or Kali Linux does not establish networking or security.
- Structural loads, reactions, percentages, comparisons, and measured outcomes do
  not automatically establish `quantitative_analysis`.
- New-node evidence has no deterministic scoring route, so taxonomy recognition
  cannot create a readiness contribution in this stage.

## Scoring routes to consider later

No scoring route was added. Human-reviewed Stage 4 examples should first establish
the positive and insufficient boundaries for each new node. Structural analysis,
structural design, mechanical design, engineering simulation, embedded/digital
systems, qualitative research, and teaching/instruction may receive separate routes
later if review supports them. Technical drafting, cloud deployment, and workflow
design need more evidence before either nodes or routes are considered.

## Answers

**A. What nodes were actually necessary?** Structural analysis, structural design,
mechanical design, engineering simulation, embedded/digital systems, qualitative
research, and teaching/instruction.

**B. Did any new node create false-positive routing?** No deterministic routing was
created for the new nodes. Recorded bare-tool and adversarial regressions remain
green. Live-model routing was not re-measured in this taxonomy-only stage.

**C. What legitimate evidence remains unmapped?** Technical drafting, cloud
deployment, and generic workflow design remain supported null-ID methods.

**D. Are we ready for Stage 4: human-reviewed dataset curation?** Yes. The nodes and
their negative boundaries are explicit enough for human adjudication, while all new
nodes and labels remain provisional and unscored.
