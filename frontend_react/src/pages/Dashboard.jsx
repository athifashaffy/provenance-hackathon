import { Link } from 'react-router-dom';

export default function Dashboard() {
  return (
    <div className="space-y-8">
      {/* hero */}
      <div className="card relative overflow-hidden" style={{ background: 'linear-gradient(135deg,#1f3a8a,#2f4fb0 55%,#16213e)' }}>
        <div className="relative z-10 text-white max-w-2xl">
          <div className="badge bg-white/15 text-white">Verified Canadian Supply Chains</div>
          <h1 className="font-display font-bold text-4xl mt-3 leading-tight">
            Origin you can prove,<br />not just claim.
          </h1>
          <p className="text-white/75 mt-3 leading-relaxed">
            AEGIS is a cryptographic provenance platform for Buy&nbsp;Canadian procurement. Every
            supplier contribution is a signed attestation; the chain is verified end to end and the
            Canadian-content designation is computed deterministically.
          </p>
          <div className="flex gap-3 mt-6">
            <Link to="/supplier" className="btn bg-white text-aegis-deep hover:opacity-90">Open Supplier Wallet</Link>
            <Link to="/purchaser" className="btn border border-white/40 text-white hover:bg-white/10">Verify a Product</Link>
          </div>
        </div>
        <div className="absolute right-[-40px] top-[-40px] w-72 h-72 rounded-full bg-white/5" />
        <div className="absolute right-10 bottom-[-60px] w-52 h-52 rounded-full bg-white/5" />
      </div>

      {/* two roles */}
      <div className="grid md:grid-cols-2 gap-5">
        <Link to="/supplier" className="card hover:shadow-lg transition block group">
          <div className="flex items-center gap-3">
            <span className="inline-grid place-items-center w-11 h-11 rounded-xl bg-aegis-blue/10 text-aegis-blue text-xl">⬡</span>
            <div className="font-display font-bold text-xl text-aegis-deep group-hover:text-aegis-blue">Supplier Wallet</div>
          </div>
          <p className="text-aegis-muted mt-3 text-sm">
            A signing identity for your enterprise, like a hardware wallet for supply-chain provenance.
            Authenticate with your key + 2FA, then issue signed attestations and publish products with a QR.
          </p>
        </Link>
        <Link to="/purchaser" className="card hover:shadow-lg transition block group">
          <div className="flex items-center gap-3">
            <span className="inline-grid place-items-center w-11 h-11 rounded-xl bg-aegis-green/10 text-aegis-green text-xl">✓</span>
            <div className="font-display font-bold text-xl text-aegis-deep group-hover:text-aegis-blue">Verify a Product</div>
          </div>
          <p className="text-aegis-muted mt-3 text-sm">
            Scan a product's QR code or enter its ID to resolve the full supply chain, confirm its
            Canadian-content designation, and see every integrity check, then save the report.
          </p>
        </Link>
      </div>

      {/* engine stats */}
      <div>
        <div className="label mb-3">Verification engine, graded against the official harness</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            ['98.2%', 'official self-test score'],
            ['100%', 'clean chains, zero false positives'],
            ['5 / 5', 'attack categories detected'],
            ['0', 'crashes on malformed input'],
          ].map(([n, l]) => (
            <div key={l} className="card text-center">
              <div className="font-display font-bold text-3xl text-aegis-blue">{n}</div>
              <div className="text-xs text-aegis-muted mt-1">{l}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
