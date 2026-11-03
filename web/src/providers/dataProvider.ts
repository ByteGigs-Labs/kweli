import type { BaseRecord, DataProvider } from "@refinedev/core";
import { http } from "../lib/http";

// Minimal REST data provider (list/one/create/update/delete) using the conventions in
// docs/api-contract.md: ?_start&_end&_sort&_order and an X-Total-Count header.
// Replaces @refinedev/simple-rest, whose query-string dependency carries an unfixed advisory.
const API = "/v1";

const path = (resource: string, id?: string | number) =>
  id === undefined
    ? `${API}/${encodeURIComponent(resource)}`
    : `${API}/${encodeURIComponent(resource)}/${encodeURIComponent(String(id))}`;

export const dataProvider: DataProvider = {
  getApiUrl: () => API,

  getList: async ({ resource, pagination, sorters }) => {
    const params: Record<string, string | number> = {};
    if (pagination?.mode !== "off") {
      const current = pagination?.currentPage ?? 1;
      const size = pagination?.pageSize ?? 25;
      params._start = (current - 1) * size;
      params._end = current * size;
    }
    const sorter = sorters?.[0];
    if (sorter) {
      params._sort = sorter.field;
      params._order = sorter.order;
    }
    const response = await http.get(path(resource), { params });
    const total = Number(response.headers["x-total-count"] ?? response.data.length);
    return { data: response.data, total };
  },

  getOne: async ({ resource, id }) => ({ data: (await http.get(path(resource, id))).data }),

  create: async <TData extends BaseRecord = BaseRecord, TVariables = object>({
    resource,
    variables,
  }: {
    resource: string;
    variables: TVariables;
  }) => ({ data: (await http.post<TData>(path(resource), variables)).data }),

  update: async ({ resource, id, variables }) => ({
    data: (await http.patch(path(resource, id), variables)).data,
  }),

  deleteOne: async ({ resource, id }) => ({ data: (await http.delete(path(resource, id))).data }),
};
