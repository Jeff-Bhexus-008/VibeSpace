import { Route, Routes } from "react-router-dom";

import AppShell from "@/components/AppShell";
import ProtectedRoute from "@/components/ProtectedRoute";
import Admin from "@/pages/Admin";
import BattleCreate from "@/pages/BattleCreate";
import BattleDetail from "@/pages/BattleDetail";
import Battles from "@/pages/Battles";
import Create from "@/pages/Create";
import CreatorDashboard from "@/pages/CreatorDashboard";
import Explore from "@/pages/Explore";
import Feed from "@/pages/Feed";
import ForgotPassword from "@/pages/ForgotPassword";
import Home from "@/pages/Home";
import LearnSpace from "@/pages/LearnSpace";
import Login from "@/pages/Login";
import Messages from "@/pages/Messages";
import NotFound from "@/pages/NotFound";
import Notifications from "@/pages/Notifications";
import Profile from "@/pages/Profile";
import Register from "@/pages/Register";
import ResetPassword from "@/pages/ResetPassword";
import Settings from "@/pages/Settings";
import VerifyEmail from "@/pages/VerifyEmail";
import Watch from "@/pages/Watch";

export default function App() {
  return (
    <Routes>
      {/* public */}
      <Route element={<AppShell />}>
        <Route path="/" element={<Home />} />
        <Route path="/feed" element={<Feed />} />
        <Route path="/watch/:videoId" element={<Watch />} />
        <Route path="/battles" element={<Battles />} />
        <Route path="/battles/:challengeId" element={<BattleDetail />} />
        <Route path="/learn" element={<LearnSpace />} />
        <Route path="/explore" element={<Explore />} />
        <Route path="/u/:username" element={<Profile />} />

        {/* signed in */}
        <Route element={<ProtectedRoute />}>
          <Route path="/create" element={<Create />} />
          <Route path="/battles/new" element={<BattleCreate />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/messages" element={<Messages />} />
          <Route path="/messages/:conversationId" element={<Messages />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/creator" element={<CreatorDashboard />} />
          <Route path="/admin" element={<Admin />} />
        </Route>
      </Route>

      {/* auth */}
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}