import { http } from "../lib/http";
import { dataProvider } from "./dataProvider";

afterEach(() => vi.restoreAllMocks());

test("getList sends range and sort params and reads the total header", async () => {
  const get = vi
    .spyOn(http, "get")
    .mockResolvedValueOnce({ data: [{ id: 1 }], headers: { "x-total-count": "42" } });
  const result = await dataProvider.getList({
    resource: "clients",
    pagination: { currentPage: 2, pageSize: 10 },
    sorters: [{ field: "name", order: "asc" }],
  });
  expect(get).toHaveBeenCalledWith("/v1/clients", {
    params: { _start: 10, _end: 20, _sort: "name", _order: "asc" },
  });
  expect(result).toEqual({ data: [{ id: 1 }], total: 42 });
});

test("ids are URL-encoded", async () => {
  const get = vi.spyOn(http, "get").mockResolvedValueOnce({ data: {} });
  await dataProvider.getOne({ resource: "clients", id: "../users" });
  expect(get).toHaveBeenCalledWith("/v1/clients/..%2Fusers");
});
