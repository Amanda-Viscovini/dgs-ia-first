import { z } from "zod";

/**
 * Input contract for POST /api/query.
 *
 * Notes:
 * - `question` bounds keep the payload sane and protect the downstream context
 *   budget (ADR-0002). They are an input guard, NOT the token-budget enforcement,
 *   which lives in the prompt-builder (T-07).
 * - `history` is capped at 3 turns as a proxy for the conversation limit in
 *   ADR-0002. Real token accounting happens in T-07.
 */
export const querySchema = z
  .object({
    question: z
      .string({ required_error: "question is required" })
      .trim()
      .min(3, "question must be at least 3 characters")
      .max(1000, "question must be at most 1000 characters"),
    conversationId: z.string().uuid("conversationId must be a valid UUID").optional(),
    history: z
      .array(
        z.object({
          role: z.enum(["user", "assistant"]),
          content: z.string().trim().min(1, "history content must not be empty"),
        }),
      )
      .max(3, "history is limited to the last 3 turns (ADR-0002)")
      .optional(),
  })
  .strict(); // reject unknown fields so the input contract stays explicit

export type QueryRequest = z.infer<typeof querySchema>;

export interface FieldError {
  field: string;
  message: string;
}

export type ValidationResult =
  | { success: true; data: QueryRequest }
  | { success: false; errors: FieldError[] };

/**
 * Validates an unknown payload against the query input contract.
 * Returns a discriminated union instead of throwing, so the handler decides
 * the HTTP shape.
 */
export function validateQueryRequest(payload: unknown): ValidationResult {
  const parsed = querySchema.safeParse(payload);

  if (parsed.success) {
    return { success: true, data: parsed.data };
  }

  const errors: FieldError[] = parsed.error.issues.map((issue) => ({
    field: issue.path.join(".") || "(root)",
    message: issue.message,
  }));

  return { success: false, errors };
}
