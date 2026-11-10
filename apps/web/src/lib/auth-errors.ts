// Đổi lỗi của Supabase Auth sang câu tiếng Việt cho người dùng (US-01, thông báo lỗi tiếng Việt).
// Danh sách mã lỗi: https://supabase.com/docs/guides/auth/debugging/error-codes

type AuthErrorLike = { code?: string; status?: number; message?: string } | null | undefined;

const MESSAGES: Record<string, string> = {
  invalid_credentials: "Email hoặc mật khẩu không đúng.",
  email_not_confirmed: "Email chưa được xác nhận. Mở hộp thư và bấm link xác nhận trước khi đăng nhập.",
  user_already_exists: "Email này đã được đăng ký.",
  email_exists: "Email này đã được đăng ký.",
  weak_password: "Mật khẩu quá yếu: cần ít nhất 8 ký tự.",
  same_password: "Mật khẩu mới phải khác mật khẩu cũ.",
  over_email_send_rate_limit: "Bạn yêu cầu gửi email quá nhanh. Đợi vài phút rồi thử lại.",
  over_request_rate_limit: "Bạn thao tác quá nhanh. Đợi một chút rồi thử lại.",
  signup_disabled: "Hệ thống đang tạm khóa đăng ký mới.",
  email_address_invalid: "Địa chỉ email không hợp lệ.",
  user_banned: "Tài khoản đang bị khóa. Liên hệ quản trị viên.",
  session_expired: "Phiên đăng nhập đã hết hạn. Đăng nhập lại.",
  flow_state_expired: "Link đã hết hạn. Yêu cầu gửi lại email.",
};

export function authErrorMessage(error: AuthErrorLike): string {
  if (error?.code && MESSAGES[error.code]) return MESSAGES[error.code];
  if (error?.status === 429) return MESSAGES.over_request_rate_limit;
  return "Có lỗi xảy ra, thử lại sau.";
}
