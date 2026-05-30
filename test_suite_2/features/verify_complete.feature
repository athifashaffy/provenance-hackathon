Feature: Complete contract for the provenance verifier (micro-level)
  Exhaustive behavioural spec for POST /verify, reconciled against
  README.md, CHALLENGE.md, TECHNICAL_GUIDE.md, FAQ.md, self_test.py and the
  spec/ files. Organised by the four things the harness actually scores:
    (1) canadian_content_percentage   (within tolerance: free <=0.5, zero at >=5.0)
    (2) designation                   (exact: product_of_canada | made_in_canada | none)
    (3) anomaly detection             (F1 over flagged attestation_ids; over-flagging hurts)
    (4) anomaly classification        (bonus: type label overlap on already-matched ids)
  Plus the operational contract (schema, robustness, statelessness, latency)
  and the statistical / T4 layer (corpus-driven, not rule-driven).

  Two invariants asserted everywhere:
    * designation == "none" does NOT imply chain_valid == false. They are independent.
    * a clean chain MUST return an empty anomalies array (precision guard).

  Type labels are free-form per the FAQ: anomaly *type* is scored only as a
  bonus on attestations already matched by id. So all anomaly-type assertions
  use ACCEPTED-LABEL matching (a set of synonyms), never an exact string, except
  where the spec fixes the term.

  Background:
    Given the worked-example recovery drone chain


  # =========================================================================
  # SECTION A — Canonical serialization & hashing (TECHNICAL_GUIDE §5, FAQ)
  # Micro-level byte rules. These are unit-level but expressed as behaviour
  # because a single byte error fails every signature downstream.
  # =========================================================================

  @canonical @micro
  Scenario Outline: Canonical byte form obeys every serialization rule
    Given the canonical encoder
    When I canonically encode <input>
    Then the canonical bytes should be <expected_bytes>

    Examples:
      | input                                | expected_bytes                  |
      | {"q": 1.0, "r": 2}                   | {"q":1,"r":2}                   |
      | {"x": 520.50}                        | {"x":520.5}                     |
      | {"b": {"d": 1, "c": 2}, "a": 3}      | {"a":3,"b":{"c":2,"d":1}}       |
      | {"a": [3, 1, 2]}                     | {"a":[3,1,2]}                   |
      | {"name": "Aerospatiale-Eclair"}      | {"name":"Aerospatiale-Eclair"}  |
      | {"z": 0.0, "y": -0.0}                | {"y":0,"z":0}                   |
      | {"n": 1000000.0}                     | {"n":1000000}                   |

  @canonical @micro
  Scenario: The signature field is excluded from signed and hashed bytes
    Given any attestation
    When I change only its signature value
    Then its canonical bytes should be unchanged
    And the substring "signature" should not appear in its canonical bytes

  @canonical @micro
  Scenario Outline: Non-finite numbers are rejected from the canonical form
    Given the canonical encoder
    When I canonically encode a payload containing <bad_value>
    Then encoding should raise a value error

    Examples:
      | bad_value |
      | NaN       |
      | Infinity  |
      | -Infinity |

  @canonical @hash @micro
  Scenario: content_hash is the lowercase sha256 of the canonical signature-excluded bytes
    Given any attestation
    When I compute its content hash
    Then the content hash should be 64 lowercase hex characters
    And it should equal sha256 of the canonical signature-excluded bytes

  @canonical @hash @micro
  Scenario: Any change to parent content changes its content_hash
    Given any attestation
    When I alter any single costed field by the smallest representable amount
    Then its content hash should change


  # =========================================================================
  # SECTION B — Signatures (TECHNICAL_GUIDE §5/§8, FAQ)
  # =========================================================================

  @crypto @micro
  Scenario: A valid signature verifies against the supplier's registered key
    Given an attestation signed with the private key of its claimed supplier_id
    When I verify its signature against the registry
    Then signature verification should succeed

  @crypto @micro
  Scenario: A signature from the wrong key fails
    Given an attestation signed with a different supplier's private key
    When I verify its signature against the registry
    Then signature verification should fail

  @crypto @micro
  Scenario: A signature over mutated content fails
    Given an attestation whose payload was mutated after signing
    When I verify its signature against the registry
    Then signature verification should fail

  @crypto @threat-model @micro
  Scenario: A correctly signed but implausible chain is still caught
    Given a chain where every attestation is correctly signed
    But the chain is internally inconsistent
    When I verify the chain
    Then the chain should be invalid
    # threat model: all private keys ship; a valid signature is necessary, not sufficient


  # =========================================================================
  # SECTION C — DAG construction (TECHNICAL_GUIDE §4, FAQ "out of order")
  # =========================================================================

  @dag @clean @worked-example
  Scenario: Verify the official worked example
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the chain should be valid
    And the designation should be "made_in_canada"
    And the Canadian content percentage should be approximately 58.4
    And no anomalies should be returned

  @dag @unordered
  Scenario: Verification is independent of attestation order
    Given I shuffle the attestations so children precede parents
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the chain should be valid
    And the designation should be "made_in_canada"
    And the Canadian content percentage should be approximately 58.4
    And no anomalies should be returned

  @dag @structural @micro
  Scenario Outline: Structural DAG defects are detected on the offending node
    Given I inject structural defect "<defect>"
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the chain should be invalid
    And the offending attestation should be flagged
    And every anomaly should include an attestation id and type

    Examples:
      | defect                          |
      | dangling_parent                 |
      | circular_reference              |
      | duplicate_attestation_id        |
      | product_attestation_id_absent   |
      | parent_references_self          |
      | unreachable_orphan_node         |

  @dag @micro
  Scenario: Multiple leaves are handled without crashing
    Given a chain with more than one leaf node
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the product_attestation_id in the response should equal the requested one


  # =========================================================================
  # SECTION D — Percentage maths (TECHNICAL_GUIDE §6, FAQ "percentage is off")
  # =========================================================================

  @percentage @micro
  Scenario: Direct cost excludes labour_hours
    Given an attestation with material_cad 100, labour_cost_cad 50, labour_hours 999
    When I compute its direct cost
    Then the direct cost should be 150.0

  @percentage @micro
  Scenario: Content is attributed by performed_in_country not supplier registered_country
    Given a Canadian supplier performing one step in "US"
    And a foreign supplier performing one equal-cost step in "CA"
    When I compute the Canadian content percentage
    Then the Canadian content percentage should be approximately 50.0

  @percentage @micro
  Scenario: Percentage is a flat sum across all attestations not a weighted propagation
    Given three equal-cost CA nodes and one equal-cost foreign node in any tree shape
    When I compute the Canadian content percentage
    Then the Canadian content percentage should be approximately 75.0

  @percentage @tolerance @micro
  Scenario Outline: Percentage scoring tolerance behaves at the documented edges
    Given an expected percentage of <expected> and a reported percentage of <reported>
    When the harness scores the percentage component
    Then the percentage sub-score should be approximately <subscore>

    Examples:
      | expected | reported | subscore |
      | 58.4     | 58.4     | 1.0      |
      | 58.4     | 58.9     | 1.0      |
      | 58.4     | 53.4     | 0.0      |
      | 58.4     | 60.9     | 0.4444   |


  # =========================================================================
  # SECTION E — Designation (TECHNICAL_GUIDE §6, FAQ "designation is wrong")
  # designation == none NEVER implies chain_valid == false on a clean chain.
  # =========================================================================

  @designation @boundary
  Scenario Outline: Designation thresholds are inclusive with a Canadian last substantial transformation
    Given I adjust the chain to Canadian content percentage <percentage> with last substantial transformation country "CA"
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the chain should be valid
    And the designation should be "<designation>"
    And the Canadian content percentage should be approximately <percentage>
    And no anomalies should be returned

    Examples:
      | percentage | designation       |
      | 0.0        | none              |
      | 50.9       | none              |
      | 51.0       | made_in_canada    |
      | 51.1       | made_in_canada    |
      | 97.9       | made_in_canada    |
      | 98.0       | product_of_canada |
      | 98.1       | product_of_canada |
      | 100.0      | product_of_canada |

  @designation @transformation @boundary @micro
  Scenario Outline: Substantial transformation requires a transforming action_type AND labour_hours >= 4
    Given a last node with action_type "<action>" and labour_hours <hours> performed in "CA" at 80 percent Canadian
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the designation should be "<designation>"

    Examples:
      | action               | hours | designation    |
      | final_integration    | 4.0   | made_in_canada |
      | final_integration    | 3.9   | none           |
      | component_manufacture| 4.0   | made_in_canada |
      | subassembly          | 4.0   | made_in_canada |
      | raw_material_supply  | 50.0  | none           |

  @designation
  Scenario Outline: High Canadian content is still none when the last substantial transformation is outside Canada
    Given I adjust the chain to Canadian content percentage <percentage> with last substantial transformation country "US"
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the chain should be valid
    And the designation should be "none"
    And no anomalies should be returned

    Examples:
      | percentage |
      | 51.0       |
      | 75.0       |
      | 98.0       |
      | 99.0       |

  @designation @micro
  Scenario: The last substantial transformation is the one closest to the leaf
    Given an earlier substantial transformation in "CA" and a final one in "FR"
    When I verify the chain
    Then the designation should be "none"

  @designation
  Scenario: No substantial transformation anywhere means designation none
    Given I remove every substantial transformation from the chain
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the designation should be "none"

  @designation @zero-cost @micro
  Scenario: A zero total direct cost chain is insufficient_data and designation none but may still be a valid chain
    Given a chain whose total direct cost is zero
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the designation should be "none"
    # NOTE: this scenario deliberately makes NO claim about chain_valid.
    # designation none and chain_valid are independent; assert chain_valid only
    # against the corpus label, not by assumption.


  # =========================================================================
  # SECTION F — Mass balance (FAQ "Mass-balance false positives / misses")
  # Over-consumption is a violation; leftover is legal. Aggregate across DAG.
  # =========================================================================

  @mass-balance @micro
  Scenario: Exact consumption is clean
    Given a node producing 10 units consumed exactly by its children totalling 10
    When I verify the chain
    Then no mass balance anomaly should be reported

  @mass-balance @precision @micro
  Scenario: Leftover material (under-consumption) is legitimate and never flagged
    Given a node producing 10 units consumed only 7 in total by its children
    When I verify the chain
    Then no mass balance anomaly should be reported

  @mass-balance @micro
  Scenario: Single-edge over-consumption is flagged
    Given a node producing 10 units with one child consuming 11
    When I verify the chain
    Then the over-produced node should be flagged with an accepted mass balance type

  @mass-balance @aggregate @micro
  Scenario: Aggregate over-consumption across multiple children is flagged
    Given a node producing 10 units with two children each consuming 6
    When I verify the chain
    Then the over-produced node should be flagged with an accepted mass balance type

  @mass-balance @aggregate @precision @micro
  Scenario: Aggregate consumption within budget across multiple children is clean
    Given a node producing 10 units with two children each consuming 5
    When I verify the chain
    Then no mass balance anomaly should be reported

  @mass-balance @unit @micro
  Scenario: A child consuming in a unit other than the parent output unit is flagged
    Given a parent whose output unit is "kg" and a child consuming in "m2"
    When I verify the chain
    Then the parent node should be flagged with an accepted unit mismatch type


  # =========================================================================
  # SECTION G — Hard-rule anomaly families (single)
  # Type assertions use ACCEPTED-LABEL matching (free-form per FAQ).
  # =========================================================================

  @hard-rules @integrity
  Scenario Outline: Single hard-rule anomaly families are detected on the right attestation
    Given I inject a "<mutation>" anomaly
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the chain should be invalid
    And the injected attestation should be flagged
    And the flagged anomaly should carry an accepted type for "<family>"
    And every anomaly should include an attestation id and type

    Examples:
      | mutation                   | family               |
      | signature_invalid          | signature_invalid    |
      | signature_unknown_supplier | signature_invalid    |
      | parent_hash_mismatch       | parent_hash_mismatch |
      | timestamp_inversion        | timestamp_inversion  |
      | replay_within_chain        | replay               |


  # =========================================================================
  # SECTION H — Semantic / schema plausibility (single)
  # Note: some of these are designation/insufficient-data signals, NOT
  # necessarily chain_valid=false. Each step checks the offending id is flagged
  # but defers the chain_valid claim to the corpus where ambiguous.
  # =========================================================================

  @semantic @plausibility
  Scenario Outline: Schema-shape plausibility failures flag the offending attestation
    Given I inject semantic anomaly "<mutation>"
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the injected attestation should be flagged
    And the flagged anomaly should carry an accepted type for "<family>"
    And every anomaly should include an attestation id and type

    Examples:
      | mutation                        | family                     |
      | raw_material_has_parent         | transformation_implausible |
      | component_manufacture_no_parent | transformation_implausible |
      | subassembly_too_few_parents     | transformation_implausible |
      | final_integration_no_parents    | transformation_implausible |
      | unknown_action_type             | transformation_implausible |

  @semantic @numeric @micro
  Scenario Outline: Invalid numeric values flag the offending attestation
    Given I inject semantic anomaly "<mutation>"
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the injected attestation should be flagged
    And the flagged anomaly should carry an accepted type for "invalid_numeric_value"
    And every anomaly should include an attestation id and type

    Examples:
      | mutation                   |
      | negative_material_cost     |
      | negative_labour_cost       |
      | negative_labour_hours      |
      | negative_quantity_produced |
      | negative_quantity_consumed |
      | nan_cost_value             |


  # =========================================================================
  # SECTION I — Statistical / T4 layer (CORPUS-DRIVEN, not rule-driven)
  # These break no hard rule. Scored by F1 over t4_perturbed ids only.
  # They CANNOT be enumerated by hand; they are generated from the corpus.
  # =========================================================================

  @statistical @t4 @corpus
  Scenario: Statistical (T4) cases flag the perturbed attestations by id
    Given each labelled T4 case from the training corpus
    When I verify each chain
    Then the flagged attestation ids should match the perturbed set with F1 at or above the agreed floor
    # type label is irrelevant for T4; only the set of flagged ids is scored

  @statistical @precision @corpus
  Scenario: Clean corpus chains produce no anomalies
    Given each clean case from the training corpus
    When I verify each chain
    Then no anomalies should be returned
    And the chain should be valid


  # =========================================================================
  # SECTION J — Combined attacks (do not mask one another)
  # =========================================================================

  @combinations @pairwise
  Scenario Outline: Pairwise combined attacks are each detected
    Given I inject anomaly combination "<mutations>"
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the chain should be invalid
    And each injected attestation should be flagged
    And every anomaly should include an attestation id and type

    Examples:
      | mutations                                          |
      | signature_invalid,parent_hash_mismatch             |
      | signature_invalid,mass_balance_violation           |
      | signature_unknown_supplier,dangling_parent         |
      | dangling_parent,unit_mismatch                      |
      | mass_balance_violation,timestamp_inversion         |
      | circular_reference,replay_within_chain             |
      | parent_hash_mismatch,unit_mismatch                 |
      | signature_unknown_supplier,replay_within_chain     |
      | negative_material_cost,mass_balance_violation      |
      | timestamp_inversion,unit_mismatch                  |

  @combinations @triple
  Scenario Outline: Multi-angle triple attacks are each detected
    Given I inject anomaly combination "<mutations>"
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the chain should be invalid
    And each injected attestation should be flagged
    And every anomaly should include an attestation id and type

    Examples:
      | mutations                                                     |
      | signature_invalid,parent_hash_mismatch,mass_balance_violation |
      | signature_unknown_supplier,dangling_parent,unit_mismatch      |
      | circular_reference,timestamp_inversion,replay_within_chain    |
      | parent_hash_mismatch,unit_mismatch,negative_labour_hours      |


  # =========================================================================
  # SECTION K — Anchor registry (TECHNICAL_GUIDE §7, FAQ)
  # =========================================================================

  @anchor-registry
  Scenario: A clean unanchored chain is not automatically invalid
    Given I rewrite every attestation id to be unanchored while preserving signatures and hash links
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the chain should be valid
    And no anomalies should be returned

  @anchor-registry @micro
  Scenario: An anchored attestation whose content hash contradicts the registry is flagged
    Given an attestation whose id is anchored but whose content hash differs from the registry
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the chain should be invalid
    And the contradicting attestation should be flagged

  @anchor-registry @precision @micro
  Scenario: Absence from the registry alone is not an anomaly
    Given a clean chain none of whose ids appear in the anchor registry
    When I verify the chain
    Then no anomalies should be returned


  # =========================================================================
  # SECTION L — Response contract & robustness (TECHNICAL_GUIDE §9, FAQ)
  # =========================================================================

  @response-contract @micro
  Scenario: A valid response carries exactly the contract fields with correct types
    When I verify the chain
    Then the response should have field "product_attestation_id" of type string
    And the response should have field "canadian_content_percentage" of type number
    And the response should have field "designation" in the set product_of_canada, made_in_canada, none
    And the response should have field "chain_valid" of type boolean
    And the response should have field "anomalies" of type array
    And every anomaly should include an attestation id and type

  @response-contract @robustness @micro
  Scenario Outline: Malformed input never hangs and never crashes the service
    Given a malformed request "<request>"
    When I send it to verify
    Then the service should respond without hanging
    And it should either return a contract-valid response or a clean HTTP error

    Examples:
      | request                                  |
      | empty_attestations                       |
      | missing_product_attestation_id           |
      | product_attestation_id_not_in_array      |
      | attestation_missing_required_field       |
      | attestation_with_extra_unknown_field     |
      | not_json                                 |
      | empty_body                               |

  @response-contract @robustness
  Scenario: One bad case does not poison subsequent requests (statelessness)
    Given I send a malformed request
    And then I send the worked-example chain
    When I read the second response
    Then the response should satisfy the verifier contract
    And the designation should be "made_in_canada"

  @response-contract @performance @slow
  Scenario: The verifier sustains many sequential requests quickly
    Given the worked-example chain
    When I verify it 100 times in sequence
    Then the average latency per request should be under 1 second
    # FAQ: avoid reloading keys/models per request


  # =========================================================================
  # SECTION M — End-to-end harness parity
  # =========================================================================

  @harness @corpus @slow
  Scenario: Self-test scoring against the training corpus meets the agreed floor
    Given the full training corpus
    When I score my backend with the official per-case formula
    Then the overall score should be at or above the agreed floor
    And the clean-category over-flag rate should be at or below the agreed ceiling
