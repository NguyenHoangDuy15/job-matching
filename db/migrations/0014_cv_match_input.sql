-- =====================================================================================
--  Migration 0014 — Đọc hồ sơ CV + vector đoạn CV trong MỘT lượt gọi (S4-D05, tối ưu p95)
--  api.get_cv_match_input(p_cv_id, p_model) = api.get_cv_for_match(p_cv_id)
--                                             + "chunks": [{section, chunk_no, content, embedding}]
--  Thay hai RPC get_cv_for_match + get_cv_chunks: bớt một vòng mạng mỗi lượt Top N (~85 ms).
--  API vẫn chạy khi Supabase chưa có hàm này (dùng lại hai RPC cũ).
--  Mã lỗi như get_cv_for_match: 42501 chưa đăng nhập · P0002 không thấy CV.
--  Chạy lại nhiều lần được. Cần 0013.
-- =====================================================================================

create or replace function api.get_cv_match_input(p_cv_id uuid, p_model text)
returns jsonb
language plpgsql stable security invoker set search_path = '' as $$
begin
  return api.get_cv_for_match(p_cv_id) || jsonb_build_object(
    'chunks', coalesce((
      select jsonb_agg(jsonb_build_object('section', ch.section, 'chunk_no', ch.chunk_no,
                                          'content', ch.content,
                                          'embedding', ch.embedding::text)
                       order by ch.section, ch.chunk_no)
        from app.cv_chunks ch
       where ch.cv_id = p_cv_id and ch.model = p_model
    ), '[]'::jsonb));
end $$;

revoke execute on function api.get_cv_match_input(uuid, text) from public, anon;
grant execute on function api.get_cv_match_input(uuid, text) to authenticated;

notify pgrst, 'reload schema';
