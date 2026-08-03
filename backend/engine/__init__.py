"""Bridge simulation engine (no AI — pure Monte-Carlo + double-dummy).

Layout:
  - this package: primitives shared by every tool — constrained deal sampling
    (`sampling`, `honor_sampler`, `deal_generator`), constraint languages
    (`shapes`, `shape_parser`, `suit_quality`), `scoring`, and the single DDS
    runtime (`dds_runtime`).
  - `engine.lead`: the opening-lead simulator.
  - `engine.contract`: the optimal-contract calculator.
"""
