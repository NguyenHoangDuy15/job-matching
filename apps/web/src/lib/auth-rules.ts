// Luật phân quyền dùng chung cho proxy.ts (chạy trước khi render) và các trang (kiểm lại lần 2).
// Bảng route × vai trò: docs/ui/wireframe_auth.png (S1-H08).

export type Role = "seeker" | "hr" | "admin";
export type AccountStatus = "active" | "pending_hr" | "locked";

export type SessionInfo = {
  userId: string;
  email: string | null;
  role: Role;
  status: AccountStatus;
  orgId: string | null;
};

export const ROLE_LABEL: Record<Role, string> = {
  seeker: "Người tìm việc",
  hr: "Nhà tuyển dụng",
  admin: "Quản trị viên",
};

/** Trang chỉ dành cho khách; người đã đăng nhập vào đây sẽ được chuyển về trang chủ của mình. */
export const GUEST_ONLY_PATHS = ["/dang-nhap", "/dang-ky", "/quen-mat-khau"];

const ROLES: Role[] = ["seeker", "hr", "admin"];
const STATUSES: AccountStatus[] = ["active", "pending_hr", "locked"];

/**
 * Đọc claim do custom_access_token_hook (schema.sql v2.0) nhúng vào JWT:
 * user_role, account_status, org_id ở cấp cao nhất của claims.
 */
export function claimsToSession(claims: Record<string, unknown> | null | undefined): SessionInfo | null {
  if (!claims || typeof claims.sub !== "string") return null;
  const role = ROLES.includes(claims.user_role as Role) ? (claims.user_role as Role) : "seeker";
  const status = STATUSES.includes(claims.account_status as AccountStatus)
    ? (claims.account_status as AccountStatus)
    : "active";
  return {
    userId: claims.sub,
    email: typeof claims.email === "string" ? claims.email : null,
    role,
    status,
    orgId: typeof claims.org_id === "string" ? claims.org_id : null,
  };
}

export function homeFor(role: Role): string {
  if (role === "admin") return "/admin";
  if (role === "hr") return "/hr";
  return "/";
}

/** Vai trò được phép vào một đường dẫn; null = ai cũng vào được (kể cả khách). */
export function allowedRolesFor(pathname: string): Role[] | null {
  if (pathname === "/admin" || pathname.startsWith("/admin/")) return ["admin"];
  if (pathname === "/hr" || pathname.startsWith("/hr/")) return ["hr"];
  if (pathname.startsWith("/ho-so") || pathname.startsWith("/viec-phu-hop")) return ["seeker"];
  return null;
}

export function canAccess(session: SessionInfo, pathname: string): boolean {
  const allowed = allowedRolesFor(pathname);
  if (!allowed) return true;
  // Người đã gửi yêu cầu HR (chờ admin duyệt) được vào /hr nhưng chỉ thấy banner chờ duyệt.
  if (session.status === "pending_hr" && allowed.includes("hr")) return true;
  return allowed.includes(session.role);
}

/** Chỉ nhận đường dẫn nội bộ cho tham số ?next=, chặn chuyển hướng sang trang ngoài. */
export function safeNext(next: string | null | undefined): string | null {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return null;
  return next;
}
