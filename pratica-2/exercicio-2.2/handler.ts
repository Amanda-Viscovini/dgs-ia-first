import {
  app,
  type HttpRequest,
  type HttpResponseInit,
  type InvocationContext,
} from "@azure/functions";
import { validateQueryRequest } from "./validator.js";

/**
 * T-01 — Query endpoint scaffold + input validation.
 *
 * Scope of THIS task: parse + validate the request body and return a stubbed
 * 200 when valid. The RAG pipeline (embedding -> search -> prompt -> completion
 * -> response-builder) is wired in T-10 where the `// TODO (T-10)` marker is.
 */
export async function queryHandler(
  request: HttpRequest,
  context: InvocationContext,
): Promise<HttpResponseInit> {
  // 1. Parse the body defensively — request.json() throws on malformed JSON.
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    context.warn("query: malformed JSON body");
    return {
      status: 400,
      jsonBody: {
        error: "INVALID_JSON",
        message: "Request body must be valid JSON.",
      },
    };
  }

  // 2. Validate against the input contract.
  const result = validateQueryRequest(body);
  if (!result.success) {
    context.warn("query: input validation failed", { errors: result.errors });
    return {
      status: 400,
      jsonBody: {
        error: "VALIDATION_ERROR",
        message: "The request body did not match the expected schema.",
        details: result.errors,
      },
    };
  }

  // 3. Stubbed success. Real orchestration lands in T-10.
  // TODO (T-10): embedding -> top-5 search -> prompt (ADR-0002 budget)
  //              -> GPT-4o completion -> response-builder (source_document).
  return {
    status: 200,
    jsonBody: {
      answer: null,
      source_document: null,
      message: "Validation passed. Pipeline wiring pending (T-10).",
    },
  };
}

app.http("query", {
  methods: ["POST"],
  authLevel: "function",
  route: "query",
  handler: queryHandler,
});
