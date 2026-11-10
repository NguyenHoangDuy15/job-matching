import { defineCloudflareConfig } from "@opennextjs/cloudflare";

// Chưa bật incremental cache (R2): trang nào cũng đọc phiên đăng nhập nên render động,
// không cần lưu cache ISR. Bật R2 khi có trang tĩnh cần revalidate
// (https://opennext.js.org/cloudflare/caching).
export default defineCloudflareConfig();
