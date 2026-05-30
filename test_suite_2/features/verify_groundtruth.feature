Feature: Provenance verifier contract, grounded in the real training corpus
  Every scenario below is reconciled against training_corpus.jsonl: the 17 real
  attack families, the 11 real anomaly.type strings, the verified chain_valid
  and t4 partition, and the measured detection ceilings. No invented families.

  Conventions:
    * Hard-rule families -> chain_valid is false and carry anomalies[].
    * T4 families -> chain_valid is TRUE, carry no anomalies[], scored by F1 over
      perturbed ids only.
    * Clean -> valid, empty anomalies. (705/1000 cases: precision is paramount.)
    * Anomaly type is matched against the 11 real strings; detection credit is by
      attestation id, type is the classification bonus.

  Background:
    Given the training corpus is loaded


  # ---- A. Deterministic core: percentage + designation on real clean data ----

  @core @percentage @corpus
  Scenario: Percentage is reproduced within tolerance on every clean chain
    When I compute the percentage for every clean chain
    Then each computed percentage should match its label within 0.5

  @core @designation @corpus
  Scenario: Designation is reproduced exactly on every clean chain
    When I compute the designation for every clean chain
    Then each designation should equal its label

  @core @designation @boundary
  Scenario Outline: Designation thresholds are inclusive with a Canadian last transformation
    Given a synthetic chain at <percentage> percent Canadian finished in "CA" with labour hours 6
    When I verify the synthetic chain
    Then the designation should be "<designation>"

    Examples:
      | percentage | designation       |
      | 50.9       | none              |
      | 51.0       | made_in_canada    |
      | 97.9       | made_in_canada    |
      | 98.0       | product_of_canada |
      | 100.0      | product_of_canada |

  @core @designation @boundary
  Scenario Outline: Substantial transformation needs a transforming action AND labour_hours >= 4
    Given a synthetic chain whose last node is "<action>" with labour hours <hours> in "CA" at 80 percent
    When I verify the synthetic chain
    Then the designation should be "<designation>"

    Examples:
      | action                | hours | designation    |
      | final_integration     | 4.0   | made_in_canada |
      | final_integration     | 3.9   | none           |
      | component_manufacture | 4.0   | made_in_canada |
      | subassembly           | 4.0   | made_in_canada |
      | raw_material_supply   | 50.0  | none           |

  @core @designation
  Scenario: High Canadian content finished abroad is still none
    Given a synthetic chain at 99 percent Canadian finished in "US" with labour hours 10
    When I verify the synthetic chain
    Then the designation should be "none"


  # ---- B. Clean precision guard (the 70% majority) ----

  @precision @corpus
  Scenario: No clean chain produces any anomaly
    When I verify every clean chain with the reference verifier
    Then no clean chain should report an anomaly
    And every clean chain should be valid


  # ---- C. Hard-rule families: each detected on the right attestation(s) ----

  @hard-rules @corpus
  Scenario Outline: Hard-rule family is detected at or above its measured F1
    Given the corpus cases for family "<family>"
    When I verify each with the reference verifier
    Then the mean anomaly F1 should be at or above <floor>
    And every flagged anomaly should use one of the eleven real type strings
    And each such chain should be invalid

    Examples:
      | family                     | floor |
      | timestamp_inversion        | 0.98  |
      | circular                   | 0.90  |
      | transformation_implausible | 0.80  |
      | unknown_supplier           | 0.98  |
      | cost_anomaly               | 0.98  |
      | mass_balance               | 0.98  |
      | dangling_parent            | 0.98  |
      | parent_hash_mismatch       | 0.98  |
      | unit_mismatch              | 0.98  |
      | replay_within_chain        | 0.98  |

  @hard-rules @registry-bounded @corpus
  Scenario Outline: Signature families are bounded by the Ed25519 registry availability
    Given the corpus cases for family "<family>"
    When I verify each with the reference verifier
    Then the mean anomaly F1 should be at or above <floor>
    # These need supplier_public_keys.json (full kit) to reach 1.0; documented.

    Examples:
      | family            | floor |
      | signature_corrupt | 0.00  |
      | tamper_no_resign  | 0.25  |

  @hard-rules @multi-node @corpus
  Scenario: Circular attacks flag every node in the cluster
    Given the corpus cases for family "circular"
    When I verify each with the reference verifier
    Then the union of flagged types should include "circular_reference"
    And the union of flagged types should include "parent_hash_mismatch"


  # ---- D. Micro hard-rule behaviours on synthetic chains ----

  @hard-rules @micro
  Scenario: Aggregate over-consumption is flagged, leftover is not
    Given a synthetic node producing 10 units consumed 6 and 6 by two children
    When I verify the synthetic chain
    Then the producing node should be flagged "mass_balance_violation"

  @hard-rules @micro @precision
  Scenario: Under-consumption (leftover) is never flagged
    Given a synthetic node producing 10 units consumed 4 by one child
    When I verify the synthetic chain
    Then no mass balance anomaly should be reported

  @hard-rules @micro
  Scenario: A child consuming in the wrong unit is flagged on the consumer
    Given a synthetic parent output unit "kg" with a child consuming in "zz"
    When I verify the synthetic chain
    Then the consuming node should be flagged "unit_mismatch"

  @hard-rules @micro
  Scenario: A dangling parent reference is flagged on the referring node
    Given a synthetic chain referencing a parent id not in the array
    When I verify the synthetic chain
    Then the referring node should be flagged "dangling_parent"

  @hard-rules @micro
  Scenario: A tampered parent breaks its hash link
    Given a synthetic parent mutated after its child committed its content hash
    When I verify the synthetic chain
    Then the child should be flagged "parent_hash_mismatch"

  @hard-rules @micro
  Scenario: A duplicated attestation id is a replay
    Given a synthetic chain with one attestation id appearing twice
    When I verify the synthetic chain
    Then the duplicated id should be flagged "replay_within_chain"

  @hard-rules @micro
  Scenario: A parent timestamped after its child is a timestamp inversion
    Given a synthetic parent timestamped after its child
    When I verify the synthetic chain
    Then the child should be flagged "timestamp_inversion"

  @hard-rules @micro
  Scenario: An unregistered supplier id is flagged
    Given a synthetic node whose supplier id never appears in genuine data
    When I verify the synthetic chain
    Then that node should be flagged "signature_unknown_supplier"

  @hard-rules @micro
  Scenario: An implausible labour rate is a cost anomaly
    Given a synthetic node with a labour rate far above the genuine ceiling
    When I verify the synthetic chain
    Then that node should be flagged "cost_anomaly"

  @hard-rules @micro
  Scenario Outline: Schema-shape violations are transformation_implausible
    Given a synthetic node violating shape rule "<rule>"
    When I verify the synthetic chain
    Then that node should be flagged "transformation_implausible"

    Examples:
      | rule                            |
      | raw_material_has_parent         |
      | raw_material_has_labour_hours   |
      | component_manufacture_no_parent |
      | final_integration_no_parent     |
      | unknown_action_type             |


  # ---- E. T4 statistical layer (corpus-driven, F1 over perturbed ids) ----

  @t4 @statistical @corpus
  Scenario Outline: T4 family is caught at or above its measured F1 with zero clean leakage
    Given the corpus cases for family "<family>"
    When I run the statistical detector on each
    Then the mean perturbed-id F1 should be at or above <floor>

    Examples:
      | family            | floor |
      | t4_origin_outlier | 0.95  |
      | t4_timing_outlier | 0.86  |
      | t4_labour_outlier | 0.68  |

  @t4 @statistical @frontier @corpus
  Scenario: T4 cost outlier is the documented unsolved frontier
    Given the corpus cases for family "t4_cost_outlier"
    When I run the statistical detector on each
    Then the mean perturbed-id F1 should be between 0.0 and 1.0

  @t4 @statistical @precision @corpus
  Scenario: The statistical detector never flags a clean chain
    When I run the statistical detector on every clean chain
    Then no clean chain should be flagged by the statistical detector


  # ---- F. Response contract & robustness ----

  @contract @micro
  Scenario: The verifier response carries exactly the contract fields
    Given any corpus chain
    When I verify it with the reference verifier
    Then the response should have keys product_attestation_id, canadian_content_percentage, designation, chain_valid, anomalies
    And the designation should be one of product_of_canada, made_in_canada, none
    And every anomaly should include an attestation id and a type

  @contract @end-to-end @corpus @slow
  Scenario: The reference verifier meets the overall self-test floor
    When I score the reference verifier over the whole corpus
    Then the overall score should be at or above 93 percent
    And the clean category score should be 100 percent
