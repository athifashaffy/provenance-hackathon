import { NavLink, Outlet } from 'react-router-dom';

const tab = ({ isActive }) =>
  `px-3.5 py-1.5 rounded-lg text-sm font-semibold transition ${
    isActive ? 'bg-aegis-blue text-white shadow-sm' : 'text-aegis-muted hover:text-aegis-blue hover:bg-aegis-blue/5'
  }`;

export default function Layout() {
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 backdrop-blur bg-white/80 border-b border-aegis-line">
        <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
          <NavLink to="/" className="flex items-center gap-2.5">
            <span className="inline-grid place-items-center w-9 h-9 rounded-xl text-white font-display font-bold"
                  style={{ background: 'linear-gradient(135deg,#2f4fb0,#1f3a8a)' }}>⬡</span>
            <div>
              <div className="font-display font-bold text-lg text-aegis-deep leading-none tracking-wide">AEGIS</div>
              <div className="text-[0.65rem] text-aegis-muted tracking-wide">CRYPTOGRAPHIC PROVENANCE</div>
            </div>
          </NavLink>
          <nav className="flex gap-1 items-center">
            <NavLink to="/" end className={tab}>Dashboard</NavLink>
            <NavLink to="/supplier" className={tab}>Supplier</NavLink>
            <NavLink to="/purchaser" className={tab}>Purchaser</NavLink>
          </nav>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-6 py-8">
        <Outlet />
      </main>
      <footer className="max-w-6xl mx-auto px-6 py-8 text-xs text-aegis-muted border-t border-aegis-line mt-8">
        The Alpha Nova · AEGIS · Verified Canadian Supply Chains
      </footer>
    </div>
  );
}
