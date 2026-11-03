import type {
  AcceptLink,
  Agreement,
  AgreementInput,
  EngagementDraft,
  Invoice,
  PortalAgreement,
} from "../types";
import { http } from "./http";

export const readThread = async (thread: string) =>
  (await http.post<EngagementDraft>("/v1/agreements/extract", { thread })).data;

export const listAgreements = async () =>
  (await http.get<Agreement[]>("/v1/agreements", { params: { _start: 0, _end: 100 } })).data;

export const createAgreement = async (input: AgreementInput) =>
  (await http.post<Agreement>("/v1/agreements", input)).data;

export const getAgreement = async (id: string) =>
  (await http.get<Agreement>(`/v1/agreements/${encodeURIComponent(id)}`)).data;

export const sendAgreement = async (id: string) =>
  (await http.post<AcceptLink>(`/v1/agreements/${encodeURIComponent(id)}/send`)).data;

export const listInvoices = async () =>
  (await http.get<Invoice[]>("/v1/invoices", { params: { _start: 0, _end: 100 } })).data;

export const getInvoice = async (id: string) =>
  (await http.get<Invoice>(`/v1/invoices/${encodeURIComponent(id)}`)).data;

export const createInvoice = async (agreementId: string, dueDate: string | null) =>
  (await http.post<Invoice>("/v1/invoices", { agreement_id: agreementId, due_date: dueDate })).data;

export const sendInvoice = async (id: string) =>
  (await http.post<Invoice>(`/v1/invoices/${encodeURIComponent(id)}/send`)).data;

export const viewPortal = async (token: string) =>
  (await http.get<PortalAgreement>(`/v1/portal/agreements/${encodeURIComponent(token)}`)).data;

export const acceptPortal = async (token: string) =>
  (
    await http.post<PortalAgreement>(`/v1/portal/agreements/${encodeURIComponent(token)}/accept`, {
      accept: true,
    })
  ).data;

export const errorMessage = (failure: unknown, fallback: string) => {
  const data = (failure as { response?: { data?: { error?: { message?: string } } } }).response?.data;
  return data?.error?.message ?? fallback;
};
