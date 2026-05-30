import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'api.dart';

// ── AEGIS brand palette (matches the web UIs) ─────────────────────────────────
const kDeep = Color(0xFF1F3A8A);
const kInk = Color(0xFF16213E);
const kGreen = Color(0xFF1F6B4F);
const kAmber = Color(0xFFB8860B);
const kRed = Color(0xFFC0392B);
const kBg = Color(0xFFEEF1F7);

// Default backend = the live AEGIS deployment on Render. The app reads products,
// resolves chains, runs /verify, and loads QR codes straight from this URL.
// (Free tier spins down when idle, so the first request can take ~30-50s while
// the server wakes up — timeouts in api.dart are set generously for this.)
// You can still point it at a LAN backend (e.g. http://10.1.61.127:8000) via the
// in-app settings sheet for offline demos.
const kDefaultBaseUrl = 'https://provenance-hackathon-jcim.onrender.com';

void main() => runApp(const AegisApp());

class AegisApp extends StatelessWidget {
  const AegisApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AEGIS Scan',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        scaffoldBackgroundColor: kBg,
        colorScheme: ColorScheme.fromSeed(seedColor: kDeep),
        fontFamily: 'Roboto',
      ),
      home: const ScanScreen(),
    );
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Scan screen
// ══════════════════════════════════════════════════════════════════════════════
class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});
  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  final _controller = MobileScannerController(
    detectionSpeed: DetectionSpeed.noDuplicates,
    facing: CameraFacing.back,
  );
  late AegisApi _api = AegisApi(kDefaultBaseUrl);
  bool _busy = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _onDetect(BarcodeCapture cap) async {
    if (_busy) return;
    final code = cap.barcodes.isNotEmpty ? cap.barcodes.first.rawValue : null;
    if (code == null || code.isEmpty) return;
    await _resolve(AegisApi.extractProductId(code));
  }

  Future<void> _resolve(String productId) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final product = await _api.resolveProduct(productId);
      final chain = (product['chain'] as Map).cast<String, dynamic>();
      final verdict = await _api.verify(chain);
      final atts = (chain['attestations'] as List).cast<Map>();
      final nodes = atts
          .map((m) => ChainNode.fromJson(m.cast<String, dynamic>()))
          .toList();
      if (!mounted) return;
      await Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => ResultScreen(
            productName: (product['name'] ?? 'Product').toString(),
            publishedBy: (product['published_by'] ?? '').toString(),
            verdict: verdict,
            nodes: nodes,
          ),
        ),
      );
    } catch (e) {
      if (mounted) _snack(e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _snack(String msg) => ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(msg), backgroundColor: kRed),
      );

  /// Load and display a product's QR code straight from the live backend
  /// (GET {baseUrl}/api/qr/{productId}). Scanning this QR resolves the same
  /// product — handy for showing a code on one screen and scanning with another.
  Future<void> _showQr(String productId, String name) async {
    await showDialog<void>(
      context: context,
      builder: (ctx) => Dialog(
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(name,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                      fontWeight: FontWeight.bold, fontSize: 16, color: kInk)),
              const SizedBox(height: 4),
              Text(productId,
                  textAlign: TextAlign.center,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      fontSize: 11,
                      color: Colors.black45,
                      fontFamily: 'monospace')),
              const SizedBox(height: 16),
              // QR PNG loaded live from the AEGIS backend.
              AspectRatio(
                aspectRatio: 1,
                child: Image.network(
                  _api.qrUrl(productId),
                  fit: BoxFit.contain,
                  gaplessPlayback: true,
                  loadingBuilder: (c, child, progress) => progress == null
                      ? child
                      : const Center(child: CircularProgressIndicator()),
                  errorBuilder: (c, e, st) => const Center(
                    child: Padding(
                      padding: EdgeInsets.all(24),
                      child: Text('Could not load QR from backend',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: kRed)),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Text('Scan this code to verify the product',
                  style: TextStyle(
                      color: Colors.black.withValues(alpha: 0.6), fontSize: 12)),
              const SizedBox(height: 8),
              Align(
                alignment: Alignment.centerRight,
                child: TextButton(
                  onPressed: () => Navigator.pop(ctx),
                  child: const Text('Close'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: kInk,
      body: Stack(
        fit: StackFit.expand,
        children: [
          MobileScanner(controller: _controller, onDetect: _onDetect),
          // dim + reticle
          const _ScannerOverlay(),
          // top bar
          SafeArea(
            child: Column(
              children: [
                _TopBar(
                  onSettings: _openSettings,
                  onList: _openProductPicker,
                  onTorch: () => _controller.toggleTorch(),
                ),
                const Spacer(),
                Padding(
                  padding: const EdgeInsets.only(bottom: 36),
                  child: Column(
                    children: [
                      const Text('Scan a product QR code',
                          style: TextStyle(
                              color: Colors.white,
                              fontSize: 18,
                              fontWeight: FontWeight.w600)),
                      const SizedBox(height: 6),
                      Text('Cryptographic provenance · live verification',
                          style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.7),
                              fontSize: 13)),
                      const SizedBox(height: 18),
                      OutlinedButton.icon(
                        onPressed: _openProductPicker,
                        icon: const Icon(Icons.list_alt, color: Colors.white),
                        label: const Text('Pick a published product',
                            style: TextStyle(color: Colors.white)),
                        style: OutlinedButton.styleFrom(
                            side: BorderSide(
                                color: Colors.white.withValues(alpha: 0.6))),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          if (_busy)
            Container(
              color: Colors.black54,
              child: const Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    CircularProgressIndicator(color: Colors.white),
                    SizedBox(height: 16),
                    Text('Resolving chain & verifying…',
                        style: TextStyle(color: Colors.white)),
                    SizedBox(height: 6),
                    Text('(waking the server can take ~30s on first use)',
                        style: TextStyle(color: Colors.white70, fontSize: 12)),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }

  Future<void> _openSettings() async {
    final ctrl = TextEditingController(text: _api.baseUrl);
    final result = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) => Padding(
        padding: EdgeInsets.only(
            left: 20,
            right: 20,
            top: 20,
            bottom: MediaQuery.of(ctx).viewInsets.bottom + 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Backend URL',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
            const SizedBox(height: 4),
            const Text('The AEGIS server reachable from this phone.',
                style: TextStyle(color: Colors.black54, fontSize: 13)),
            const SizedBox(height: 14),
            TextField(
              controller: ctrl,
              autocorrect: false,
              keyboardType: TextInputType.url,
              decoration: const InputDecoration(
                  border: OutlineInputBorder(),
                  hintText: 'https://provenance-hackathon-jcim.onrender.com'),
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                style: FilledButton.styleFrom(backgroundColor: kDeep),
                onPressed: () => Navigator.pop(ctx, ctrl.text.trim()),
                child: const Text('Save'),
              ),
            ),
          ],
        ),
      ),
    );
    if (result != null && result.isNotEmpty) {
      setState(() => _api = AegisApi(result));
      final ok = await _api.health();
      if (mounted) {
        _snack(ok ? 'Connected to backend ✓' : 'Could not reach backend');
      }
    }
  }

  Future<void> _openProductPicker() async {
    List<Map<String, dynamic>> items = [];
    try {
      items = await _api.listProducts();
    } catch (_) {}
    if (!mounted) return;
    final pid = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: Colors.white,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.6,
        maxChildSize: 0.9,
        builder: (_, scroll) => Column(
          children: [
            const SizedBox(height: 12),
            Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                    color: Colors.black26,
                    borderRadius: BorderRadius.circular(2))),
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('Published products',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
            ),
            Expanded(
              child: items.isEmpty
                  ? const Center(child: Text('No products found.'))
                  : ListView.separated(
                      controller: scroll,
                      itemCount: items.length,
                      separatorBuilder: (_, __) => const Divider(height: 1),
                      itemBuilder: (_, i) {
                        final p = items[i];
                        final pid = (p['product_id'] ?? '').toString();
                        final name = (p['name'] ?? 'Product').toString();
                        return ListTile(
                          leading: const Icon(Icons.inventory_2_outlined,
                              color: kDeep),
                          title: Text(name),
                          subtitle: Text(pid,
                              maxLines: 1, overflow: TextOverflow.ellipsis),
                          trailing: IconButton(
                            tooltip: 'Show QR code',
                            icon: const Icon(Icons.qr_code_2, color: kDeep),
                            onPressed: () => _showQr(pid, name),
                          ),
                          onTap: () => Navigator.pop(ctx, pid),
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
    if (pid != null) await _resolve(pid);
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar(
      {required this.onSettings, required this.onList, required this.onTorch});
  final VoidCallback onSettings, onList, onTorch;
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 8, 0),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(7),
            decoration: BoxDecoration(
                color: kDeep, borderRadius: BorderRadius.circular(9)),
            child: const Icon(Icons.shield_outlined,
                color: Colors.white, size: 20),
          ),
          const SizedBox(width: 10),
          const Text('AEGIS',
              style: TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 1.5)),
          const Spacer(),
          IconButton(
              onPressed: onTorch,
              icon: const Icon(Icons.flash_on, color: Colors.white)),
          IconButton(
              onPressed: onList,
              icon: const Icon(Icons.list_alt, color: Colors.white)),
          IconButton(
              onPressed: onSettings,
              icon: const Icon(Icons.settings, color: Colors.white)),
        ],
      ),
    );
  }
}

class _ScannerOverlay extends StatelessWidget {
  const _ScannerOverlay();
  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, c) {
      final box = math.min(c.maxWidth, c.maxHeight) * 0.66;
      return Center(
        child: Container(
          width: box,
          height: box,
          decoration: BoxDecoration(
            border:
                Border.all(color: Colors.white.withValues(alpha: 0.9), width: 3),
            borderRadius: BorderRadius.circular(20),
          ),
        ),
      );
    });
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Result screen
// ══════════════════════════════════════════════════════════════════════════════
class ResultScreen extends StatelessWidget {
  const ResultScreen({
    super.key,
    required this.productName,
    required this.publishedBy,
    required this.verdict,
    required this.nodes,
  });

  final String productName;
  final String publishedBy;
  final VerifyResult verdict;
  final List<ChainNode> nodes;

  ({String label, Color color, IconData icon}) get _desig {
    switch (verdict.designation) {
      case 'product_of_canada':
        return (label: 'Product of Canada', color: kGreen, icon: Icons.verified);
      case 'made_in_canada':
        return (label: 'Made in Canada', color: kDeep, icon: Icons.flag);
      default:
        return (
          label: 'Not Qualified',
          color: kAmber,
          icon: Icons.remove_circle_outline
        );
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = _desig;
    final hasAnomalies = verdict.anomalies.isNotEmpty;
    final trusted = verdict.chainValid && !hasAnomalies;

    return Scaffold(
      appBar: AppBar(
        backgroundColor: kInk,
        foregroundColor: Colors.white,
        title: const Text('Provenance Report'),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 40),
        children: [
          // ── Trust banner ──
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: trusted ? kGreen : kRed,
              borderRadius: BorderRadius.circular(14),
            ),
            child: Row(
              children: [
                Icon(trusted ? Icons.gpp_good : Icons.gpp_bad,
                    color: Colors.white, size: 30),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                          trusted
                              ? 'Chain verified — cryptographically intact'
                              : 'Integrity problem detected',
                          style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.bold,
                              fontSize: 15)),
                      Text(
                          trusted
                              ? 'All signatures valid · no anomalies'
                              : '${verdict.anomalies.length} anomaly(ies) · chain_valid=${verdict.chainValid}',
                          style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.9),
                              fontSize: 12)),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Text(productName,
              style: const TextStyle(
                  fontSize: 22, fontWeight: FontWeight.bold, color: kInk)),
          if (publishedBy.isNotEmpty)
            Text('published by $publishedBy',
                style: const TextStyle(color: Colors.black54, fontSize: 13)),
          const SizedBox(height: 18),

          // ── Gauge + designation ──
          Card(
            elevation: 0,
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            child: Padding(
              padding: const EdgeInsets.all(18),
              child: Row(
                children: [
                  _Gauge(pct: verdict.percentage, color: d.color),
                  const SizedBox(width: 20),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('DESIGNATION',
                            style: TextStyle(
                                color: Colors.black45,
                                fontSize: 11,
                                fontWeight: FontWeight.bold,
                                letterSpacing: 1)),
                        const SizedBox(height: 6),
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 12, vertical: 8),
                          decoration: BoxDecoration(
                              color: d.color.withValues(alpha: 0.12),
                              borderRadius: BorderRadius.circular(10)),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(d.icon, color: d.color, size: 18),
                              const SizedBox(width: 6),
                              Flexible(
                                child: Text(d.label,
                                    style: TextStyle(
                                        color: d.color,
                                        fontWeight: FontWeight.bold,
                                        fontSize: 15)),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 10),
                        Text('Canadian content',
                            style: TextStyle(
                                color: Colors.black.withValues(alpha: 0.6),
                                fontSize: 12)),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 18),

          // ── Anomalies ──
          if (hasAnomalies) ...[
            const _SectionTitle('Detected anomalies'),
            ...verdict.anomalies.map((a) => _AnomalyCard(a)),
            const SizedBox(height: 8),
          ],

          // ── Provenance chain ──
          const _SectionTitle('Provenance chain'),
          const SizedBox(height: 4),
          ..._sortedNodes().asMap().entries.map((e) => _NodeTile(
                node: e.value,
                isLast: e.key == nodes.length - 1,
                flagged:
                    verdict.anomalies.any((a) => a.attestationId == e.value.id),
              )),
        ],
      ),
    );
  }

  // raw_material first → final_integration last
  List<ChainNode> _sortedNodes() {
    const order = {
      'raw_material_supply': 0,
      'component_manufacture': 1,
      'subassembly': 2,
      'final_integration': 3,
    };
    final list = [...nodes];
    list.sort((a, b) =>
        (order[a.actionType] ?? 9).compareTo(order[b.actionType] ?? 9));
    return list;
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.text);
  final String text;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 8, top: 4),
        child: Text(text.toUpperCase(),
            style: const TextStyle(
                color: Colors.black54,
                fontWeight: FontWeight.bold,
                fontSize: 12,
                letterSpacing: 1)),
      );
}

class _AnomalyCard extends StatelessWidget {
  const _AnomalyCard(this.a);
  final Anomaly a;
  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: kRed.withValues(alpha: 0.06),
        border: Border.all(color: kRed.withValues(alpha: 0.4)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.warning_amber_rounded, color: kRed, size: 18),
              const SizedBox(width: 8),
              Expanded(
                child: Text(a.type.replaceAll('_', ' ').toUpperCase(),
                    style: const TextStyle(
                        color: kRed,
                        fontWeight: FontWeight.bold,
                        fontSize: 13)),
              ),
            ],
          ),
          if (a.details.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(a.details, style: const TextStyle(fontSize: 13, color: kInk)),
          ],
          if (a.attestationId.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(a.attestationId,
                style: const TextStyle(
                    fontSize: 11,
                    color: Colors.black45,
                    fontFamily: 'monospace')),
          ],
        ],
      ),
    );
  }
}

class _NodeTile extends StatelessWidget {
  const _NodeTile(
      {required this.node, required this.isLast, required this.flagged});
  final ChainNode node;
  final bool isLast;
  final bool flagged;

  String get _action => node.actionType.replaceAll('_', ' ');

  @override
  Widget build(BuildContext context) {
    final dot = flagged ? kRed : (node.isCanadian ? kGreen : kAmber);
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // timeline rail
          Column(
            children: [
              Container(
                width: 14,
                height: 14,
                margin: const EdgeInsets.only(top: 18),
                decoration: BoxDecoration(color: dot, shape: BoxShape.circle),
              ),
              if (!isLast)
                Expanded(
                    child: Container(
                        width: 2,
                        color: Colors.black.withValues(alpha: 0.12))),
            ],
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Container(
              margin: const EdgeInsets.only(bottom: 10),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                    color: flagged
                        ? kRed.withValues(alpha: 0.5)
                        : Colors.black.withValues(alpha: 0.08)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(node.outputName,
                            style: const TextStyle(
                                fontWeight: FontWeight.bold,
                                fontSize: 14,
                                color: kInk)),
                      ),
                      _CountryChip(
                          country: node.country, canadian: node.isCanadian),
                    ],
                  ),
                  const SizedBox(height: 3),
                  Text('$_action · ${node.supplier}',
                      style:
                          const TextStyle(fontSize: 12, color: Colors.black54)),
                  const SizedBox(height: 6),
                  Text(
                      'CA\$${node.directCost.toStringAsFixed(0)} direct'
                      '${node.labourHours > 0 ? ' · ${node.labourHours.toStringAsFixed(1)}h labour' : ''}',
                      style:
                          const TextStyle(fontSize: 12, color: Colors.black45)),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _CountryChip extends StatelessWidget {
  const _CountryChip({required this.country, required this.canadian});
  final String country;
  final bool canadian;
  @override
  Widget build(BuildContext context) {
    final c = canadian ? kGreen : Colors.black45;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
          color: c.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(20)),
      child: Text(canadian ? '🇨🇦 $country' : country,
          style:
              TextStyle(color: c, fontWeight: FontWeight.bold, fontSize: 12)),
    );
  }
}

class _Gauge extends StatelessWidget {
  const _Gauge({required this.pct, required this.color});
  final double pct;
  final Color color;
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 92,
      height: 92,
      child: Stack(
        alignment: Alignment.center,
        children: [
          SizedBox(
            width: 92,
            height: 92,
            child: CircularProgressIndicator(
              value: (pct / 100).clamp(0.0, 1.0),
              strokeWidth: 9,
              backgroundColor: Colors.black.withValues(alpha: 0.08),
              valueColor: AlwaysStoppedAnimation(color),
            ),
          ),
          Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(pct.toStringAsFixed(1),
                  style: TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.bold,
                      color: color)),
              const Text('%',
                  style: TextStyle(fontSize: 12, color: Colors.black54)),
            ],
          ),
        ],
      ),
    );
  }
}
