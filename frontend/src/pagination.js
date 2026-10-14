export const DEFAULT_PAGE_SIZE = 5
export const DEFAULT_OVERVIEW_PAGE_SIZE = 10
export const PAGE_SIZES = [5, 10, 15, 20, 30, 50]

export function pageSlice(rows, page, pageSize) {
  return rows.slice((page - 1) * pageSize, page * pageSize)
}
