Feature: Packed contract for the provenance verifier
  This single packed BDD feature captures the behaviour described across
  README.md, CHALLENGE.md, TECHNICAL_GUIDE.md, spec/attestation-schema.md,
  spec/computation.md, and spec/anchor-registry.md.

  Background:
    Given the worked-example recovery drone chain

  @spec @clean @worked-example
  Scenario: Verify the official worked example
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the chain should be valid
    And the designation should be "made_in_canada"
    And the Canadian content percentage should be approximately 58.4
    And no anomalies should be returned

  @spec @unordered
  Scenario: Verification is independent of attestation order
    Given I shuffle the attestations
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the chain should be valid
    And the designation should be "made_in_canada"
    And the Canadian content percentage should be approximately 58.4
    And no anomalies should be returned

  @spec @anchor-registry
  Scenario: A clean unanchored chain is not automatically invalid
    Given I rewrite every attestation id to be unanchored while preserving signatures and hash links
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the chain should be valid
    And no anomalies should be returned

  @spec @designation
  Scenario Outline: Canadian designation threshold boundaries require a Canadian last substantial transformation
    Given I adjust the chain to Canadian content percentage <percentage> with last substantial transformation country "CA"
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the chain should be valid
    And the designation should be "<designation>"
    And the Canadian content percentage should be approximately <percentage>
    And no anomalies should be returned

    Examples:
      | percentage | designation       |
      | 50.9       | none              |
      | 51.0       | made_in_canada    |
      | 51.1       | made_in_canada    |
      | 97.9       | made_in_canada    |
      | 98.0       | product_of_canada |
      | 98.1       | product_of_canada |

  @spec @designation
  Scenario Outline: High Canadian content is still none when last substantial transformation is outside Canada
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

  @spec @designation
  Scenario: No substantial transformation means no Canadian designation
    Given I remove every substantial transformation from the chain
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the chain should be valid
    And the designation should be "none"

  @hard-rules @crypto @integrity
  Scenario Outline: Single hard-rule anomaly families are detected
    Given I inject a "<mutation>" anomaly
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the chain should be invalid
    And the response should contain anomaly type "<expected_type>"
    And every anomaly should include an attestation id and type

    Examples:
      | mutation                   | expected_type               |
      | signature_invalid          | signature_invalid           |
      | signature_unknown_supplier | signature_unknown_supplier  |
      | parent_hash_mismatch       | parent_hash_mismatch        |
      | dangling_parent            | dangling_parent             |
      | timestamp_inversion        | timestamp_inversion         |
      | unit_mismatch              | unit_mismatch               |
      | mass_balance_violation     | mass_balance_violation      |
      | circular_reference         | circular_reference          |
      | replay_within_chain        | replay_within_chain         |
      | transformation_implausible | transformation_implausible  |
      | invalid_numeric_value      | invalid_numeric_value       |

  @semantic @plausibility
  Scenario Outline: Semantic and schema plausibility failures are detected
    Given I inject semantic anomaly "<mutation>"
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the chain should be invalid
    And the response should contain an accepted anomaly type for "<expected_type>"
    And every anomaly should include an attestation id and type

    Examples:
      | mutation                         | expected_type              |
      | raw_material_has_parent          | transformation_implausible |
      | component_manufacture_no_parent  | transformation_implausible |
      | subassembly_too_few_parents      | transformation_implausible |
      | final_integration_no_parents     | transformation_implausible |
      | unknown_action_type              | transformation_implausible |
      | negative_material_cost           | invalid_numeric_value      |
      | negative_labour_cost             | invalid_numeric_value      |
      | negative_labour_hours            | invalid_numeric_value      |
      | negative_quantity_produced       | invalid_numeric_value      |
      | negative_quantity_consumed       | invalid_numeric_value      |
      | labour_cost_with_zero_hours      | cost_anomaly               |
      | implausibly_high_unit_cost       | cost_anomaly               |
      | zero_total_direct_cost           | insufficient_data          |

  @combinations @pairwise
  Scenario Outline: Pairwise combined attacks are detected without hiding each other
    Given I inject anomaly combination "<mutations>"
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the chain should be invalid
    And the response should contain each anomaly type from "<mutations>"
    And every anomaly should include an attestation id and type

    Examples:
      | mutations                                                         |
      | signature_invalid,parent_hash_mismatch                            |
      | signature_invalid,mass_balance_violation                          |
      | signature_unknown_supplier,dangling_parent                         |
      | dangling_parent,unit_mismatch                                      |
      | mass_balance_violation,timestamp_inversion                         |
      | circular_reference,replay_within_chain                             |
      | cost_anomaly,transformation_implausible                            |
      | invalid_numeric_value,cost_anomaly                                 |
      | parent_hash_mismatch,unit_mismatch                                 |
      | signature_unknown_supplier,replay_within_chain                      |

  @combinations @triple
  Scenario Outline: Multi-angle triple attacks are detected
    Given I inject anomaly combination "<mutations>"
    When I verify the chain
    Then the response should satisfy the verifier contract
    And the chain should be invalid
    And the response should contain each anomaly type from "<mutations>"
    And every anomaly should include an attestation id and type

    Examples:
      | mutations                                                               |
      | signature_invalid,parent_hash_mismatch,mass_balance_violation            |
      | signature_unknown_supplier,dangling_parent,unit_mismatch                 |
      | circular_reference,timestamp_inversion,replay_within_chain               |
      | cost_anomaly,transformation_implausible,invalid_numeric_value            |

  @response-contract
  Scenario: Every invalid response still follows the verifier response contract
    Given I inject anomaly combination "signature_invalid,parent_hash_mismatch,mass_balance_violation"
    When I verify the chain
    Then the response should satisfy the verifier contract
    And every anomaly should include an attestation id and type
