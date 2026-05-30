import 'dart:convert';
import 'package:http/http.dart' as http;

/// AEGIS backend client. Mirrors the purchaser web flow:
///   QR -> product_id -> GET /api/products/{id} (chain) -> POST /verify (verdict)
class AegisApi {
  AegisApi(this.baseUrl);

  /// The live AEGIS backend, e.g. https://provenance-hackathon-jcim.onrender.com
  String baseUrl;

  Uri _u(String path) => Uri.parse('${baseUrl.replaceAll(RegExp(r'/+$'), '')}$path');

  /// Public URL of a product's QR PNG, served by the backend.
  /// The app loads/displays this image directly from the live server.
  String qrUrl(String productId) => _u('/api/qr/$productId').toString();

  /// A scanned QR may be a deep link (.../purchaser?pid=att-...) or a bare id.
  static String extractProductId(String raw) {
    final s = raw.trim();
    final uri = Uri.tryParse(s);
    if (uri != null && uri.queryParameters['pid'] != null) {
      return uri.queryParameters['pid']!;
    }
    // last path segment if it looks like an attestation id
    final m = RegExp(r'(att-[A-Za-z0-9\-]+)').firstMatch(s);
    if (m != null) return m.group(1)!;
    return s;
  }

  Future<bool> health() async {
    try {
      final r = await http.get(_u('/health')).timeout(const Duration(seconds: 60)); // Render cold start
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// Resolve a published product -> { product_id, name, published_by, chain }
  Future<Map<String, dynamic>> resolveProduct(String productId) async {
    final r = await http
        .get(_u('/api/products/$productId'))
        .timeout(const Duration(seconds: 60)); // Render cold start
    if (r.statusCode == 404) {
      throw AegisError('No product found for "$productId". Is it published?');
    }
    if (r.statusCode != 200) {
      throw AegisError('Lookup failed (${r.statusCode}).');
    }
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  /// Run the scored verification contract on a chain payload.
  Future<VerifyResult> verify(Map<String, dynamic> chain) async {
    final r = await http
        .post(_u('/verify'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(chain))
        .timeout(const Duration(seconds: 60)); // Render cold start
    if (r.statusCode != 200) {
      throw AegisError('Verification failed (${r.statusCode}).');
    }
    return VerifyResult.fromJson(jsonDecode(r.body) as Map<String, dynamic>);
  }

  /// List published products for the demo picker fallback.
  Future<List<Map<String, dynamic>>> listProducts() async {
    final r = await http.get(_u('/api/products')).timeout(const Duration(seconds: 60)); // Render cold start
    if (r.statusCode != 200) return [];
    final list = jsonDecode(r.body) as List;
    return list.cast<Map<String, dynamic>>();
  }
}

class AegisError implements Exception {
  AegisError(this.message);
  final String message;
  @override
  String toString() => message;
}

/// One supplier step in the provenance DAG (from the chain attestations).
class ChainNode {
  ChainNode({
    required this.id,
    required this.supplier,
    required this.actionType,
    required this.country,
    required this.outputName,
    required this.materialCad,
    required this.labourCad,
    required this.labourHours,
  });

  final String id;
  final String supplier;
  final String actionType;
  final String country;
  final String outputName;
  final double materialCad;
  final double labourCad;
  final double labourHours;

  bool get isCanadian => country.toUpperCase() == 'CA';
  double get directCost => materialCad + labourCad;

  factory ChainNode.fromJson(Map<String, dynamic> j) {
    final costs = (j['costs'] as Map?) ?? const {};
    final output = (j['output'] as Map?) ?? const {};
    double d(dynamic v) => (v is num) ? v.toDouble() : 0.0;
    return ChainNode(
      id: (j['attestation_id'] ?? '').toString(),
      supplier: (j['supplier_id'] ?? 'unknown').toString(),
      actionType: (j['action_type'] ?? '').toString(),
      country: (j['performed_in_country'] ?? '??').toString(),
      outputName: (output['name'] ?? 'Component').toString(),
      materialCad: d(costs['material_cad']),
      labourCad: d(costs['labour_cost_cad']),
      labourHours: d(costs['labour_hours']),
    );
  }
}

/// Response of POST /verify.
class VerifyResult {
  VerifyResult({
    required this.productId,
    required this.percentage,
    required this.designation,
    required this.chainValid,
    required this.anomalies,
  });

  final String productId;
  final double percentage;
  final String designation; // product_of_canada | made_in_canada | none
  final bool chainValid;
  final List<Anomaly> anomalies;

  factory VerifyResult.fromJson(Map<String, dynamic> j) {
    final raw = (j['anomalies'] as List?) ?? const [];
    return VerifyResult(
      productId: (j['product_attestation_id'] ?? '').toString(),
      percentage: ((j['canadian_content_percentage'] ?? 0) as num).toDouble(),
      designation: (j['designation'] ?? 'none').toString(),
      chainValid: j['chain_valid'] == true,
      anomalies: raw
          .map((e) => Anomaly.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class Anomaly {
  Anomaly({required this.type, required this.attestationId, required this.details});
  final String type;
  final String attestationId;
  final String details;

  factory Anomaly.fromJson(Map<String, dynamic> j) => Anomaly(
        type: (j['type'] ?? 'anomaly').toString(),
        attestationId: (j['attestation_id'] ?? '').toString(),
        details: (j['details'] ?? '').toString(),
      );
}
