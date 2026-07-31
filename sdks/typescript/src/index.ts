export type AuthorizationDecision = {
  decision: boolean;
  context?: {
    reason?: string;
    receipt?: { id?: string };
    obligations?: Array<{
      id: string;
      required?: boolean;
      parameters?: Record<string, unknown>;
    }>;
  };
};

export class EnforcementDenied extends Error {}

type ObligationHandler = (
  parameters: Record<string, unknown>,
  decision: AuthorizationDecision,
) => void | Promise<void>;

export class OpenDataGraphPEP {
  private readonly handlers = new Map<string, ObligationHandler>();

  constructor(
    private readonly baseUrl: string,
    private readonly pepId: string,
    private readonly options: {
      apiKey?: string;
      bearerToken?: string;
      fetch?: typeof globalThis.fetch;
    } = {},
  ) {}

  registerObligation(id: string, handler: ObligationHandler): void {
    this.handlers.set(id, handler);
  }

  async evaluate(request: {
    subject: Record<string, unknown>;
    resource: Record<string, unknown>;
    action: Record<string, unknown>;
    context?: Record<string, unknown>;
    idempotencyKey?: string;
  }): Promise<AuthorizationDecision> {
    return this.post(
      "/access/v1/evaluation",
      {
        subject: request.subject,
        resource: request.resource,
        action: request.action,
        context: request.context ?? {},
      },
      request.idempotencyKey ? { "Idempotency-Key": request.idempotencyKey } : {},
    );
  }

  async enforce<T>(
    decision: AuthorizationDecision,
    operation: () => T | Promise<T>,
    metadata: Record<string, unknown> = {},
  ): Promise<T> {
    const receiptId = decision.context?.receipt?.id;
    if (!receiptId) throw new Error("Authorization decision does not contain a receipt id");
    if (!decision.decision) {
      const reason = decision.context?.reason ?? "OpenDataGraph policy denied the operation";
      await this.report(receiptId, "rejected", [], reason, metadata);
      throw new EnforcementDenied(reason);
    }
    const obligations = (decision.context?.obligations ?? []).filter(
      (item) => item.required !== false && item.id,
    );
    const satisfied: string[] = [];
    try {
      for (const obligation of obligations) {
        const handler = this.handlers.get(obligation.id);
        if (!handler) {
          throw new EnforcementDenied(
            `No enforcement handler is registered for required obligation ${obligation.id}`,
          );
        }
        await handler(obligation.parameters ?? {}, decision);
        satisfied.push(obligation.id);
      }
      const result = await operation();
      await this.report(receiptId, "applied", satisfied, undefined, metadata);
      return result;
    } catch (error) {
      await this.report(
        receiptId,
        "failed",
        satisfied,
        error instanceof Error ? error.message : String(error),
        metadata,
      );
      throw error;
    }
  }

  private report(
    receiptId: string,
    outcome: "applied" | "rejected" | "failed",
    satisfiedObligations: string[],
    failureReason: string | undefined,
    metadata: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return this.post("/api/v1/runtime/enforcement-events", {
      event_id: crypto.randomUUID(),
      receipt_id: receiptId,
      pep_id: this.pepId,
      outcome,
      satisfied_obligations: satisfiedObligations,
      failure_reason: failureReason,
      metadata,
      occurred_at: new Date().toISOString(),
    });
  }

  private async post<T>(
    path: string,
    body: Record<string, unknown>,
    extraHeaders: Record<string, string> = {},
  ): Promise<T> {
    const fetcher = this.options.fetch ?? globalThis.fetch;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "X-Request-ID": crypto.randomUUID(),
      ...extraHeaders,
    };
    if (this.options.bearerToken) headers.Authorization = `Bearer ${this.options.bearerToken}`;
    else if (this.options.apiKey) headers["X-API-Key"] = this.options.apiKey;
    const response = await fetcher(`${this.baseUrl.replace(/\/$/, "")}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw new Error(`OpenDataGraph returned HTTP ${response.status}: ${(await response.text()).slice(0, 2000)}`);
    }
    return (await response.json()) as T;
  }
}
