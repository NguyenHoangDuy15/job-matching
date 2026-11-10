import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Tắt Cache Components: gần như mọi trang đều đọc cookie phiên đăng nhập, bật lên thì
  // phải bọc từng chỗ đọc phiên trong <Suspense>. Bật lại khi cần tối ưu (xem
  // node_modules/next/dist/docs/01-app/02-guides/authentication-with-cache-components.md).
  cacheComponents: false,
  images: {
    // Cloudflare Workers không có tối ưu ảnh mặc định của Next.js.
    unoptimized: true,
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
