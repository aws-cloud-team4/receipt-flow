import { useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api, type Me } from "./api";
import { setStoreOwner } from "./userStore";
import { HelpProvider } from "./components/Help";
import { isSignedIn, signOut } from "./auth";
import Shell from "./components/Shell";
import EmployeeDashboard from "./pages/EmployeeDashboard";
import ReviewerDashboard from "./pages/ReviewerDashboard";
import EmployeeHome from "./pages/EmployeeHome";
import AdminReceipts from "./pages/AdminReceipts";
import AdminUsers from "./pages/AdminUsers";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import NewReceipt from "./pages/NewReceipt";
import Profile from "./pages/Profile";
import ReceiptWorkspace from "./pages/ReceiptWorkspace";
import ReviewDetail from "./pages/ReviewDetail";
import ReviewHome from "./pages/ReviewHome";

export default function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(isSignedIn());
  const navigate = useNavigate();

  const loadMe = useCallback(async () => {
    if (!isSignedIn()) return;
    setLoading(true);
    try {
      const m = await api.me();
      setStoreOwner(m.sub);
      setMe(m);
    } catch {
      signOut();
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  // Once on start. (navigate changes on every route change; with it here every click refetched the
  // profile and remounted the whole app behind "불러오는 중".)
  useEffect(() => {
    loadMe();
  }, [loadMe]);

  useEffect(() => {
    const onUnauthorized = () => {
      signOut();
      setMe(null);
      navigate("/login");
    };
    window.addEventListener("rf:unauthorized", onUnauthorized);
    return () => window.removeEventListener("rf:unauthorized", onUnauthorized);
  }, [navigate]);

  if (loading) return <div className="empty">불러오는 중…</div>;
  if (!me) {
    return (
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/about" element={<Landing />} />
        <Route path="/login" element={<Login onSignedIn={loadMe} />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  const logout = () => {
    signOut();
    setMe(null);
    navigate("/login");
  };

  // every signed-in page except the intro sits in the app shell (top bar, side menu, help)
  const app = (
    <HelpProvider>
    <Shell me={me} onLogout={logout}>
      <Routes>
        <Route path="/me" element={<Profile me={me} />} />
        {me.role === "admin" ? (
          <>
            <Route path="/" element={<AdminUsers me={me} />} />
            <Route path="/admin/receipts" element={<AdminReceipts />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </>
        ) : me.role === "reviewer" ? (
          <>
            <Route path="/" element={<ReviewerDashboard me={me} />} />
            <Route path="/review" element={<ReviewHome />} />
            <Route path="/review/:id" element={<ReviewDetail me={me} />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </>
        ) : (
          <>
            <Route path="/" element={<EmployeeDashboard me={me} />} />
            <Route path="/receipts" element={<EmployeeHome />} />
            <Route path="/new" element={<NewReceipt />} />
            <Route path="/receipts/:id" element={<ReceiptWorkspace />} />
            <Route path="/receipts/:id/photo" element={<NewReceipt />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </>
        )}
      </Routes>
    </Shell>
    </HelpProvider>
  );

  return (
    <Routes>
      {/* the intro page, full screen and outside the app shell; it offers a way back home */}
      <Route path="/about" element={<Landing me={me} />} />
      <Route path="/*" element={app} />
    </Routes>
  );
}
