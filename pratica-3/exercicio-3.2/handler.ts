import { app, HttpRequest, HttpResponseInit, InvocationContext } from '@azure/functions';
import { CosmosClient } from '@azure/cosmos'; // import estático no topo
import { logger } from '../../shared/logger'; // pino, nunca console.log
import { config } from '../../shared/config'; // env validada no boot
import { feedbackSchema } from './validator';

// Singleton de módulo — criado uma vez por processo, reusado entre invocações.
const container = new CosmosClient(config.cosmosConnectionString)
  .database('novatech')
  .container('feedbacks');

export async function feedbackHandler(
  request: HttpRequest,
  context: InvocationContext,
): Promise<HttpResponseInit> {
  // Parse defensivo do corpo
  let rawBody: unknown; // nada de `as any`
  try {
    rawBody = await request.json();
  } catch {
    logger.warn({ requestId: context.invocationId }, 'Feedback com JSON inválido');
    return { status: 400, jsonBody: { error: 'INVALID_JSON' } };
  }

  // Validação Zod antes de qualquer uso
  const parsed = feedbackSchema.safeParse(rawBody);
  if (!parsed.success) {
    // Loga só caminho+código dos erros, nunca os valores enviados (PII)
    logger.warn(
      {
        requestId: context.invocationId,
        issues: parsed.error.issues.map((i) => ({ path: i.path, code: i.code })),
      },
      'Feedback rejeitado na validação',
    );
    return { status: 400, jsonBody: { error: 'VALIDATION_FAILED' } };
  }

  const feedback = { ...parsed.data, timestamp: new Date().toISOString() };

  // Persistência com tratamento de erro
  try {
    await container.items.create(feedback);
  } catch (err) {
    logger.error(
      { requestId: context.invocationId, queryId: feedback.queryId, err },
      'Falha ao persistir feedback',
    );
    return { status: 500, jsonBody: { error: 'PERSISTENCE_FAILED' } };
  }

  // Log de sucesso SEM dados pessoais (sem attendantEmail, sem comment)
  logger.info(
    { requestId: context.invocationId, queryId: feedback.queryId, rating: feedback.rating },
    'Feedback registrado',
  );

  return { status: 201, jsonBody: { status: 'created' } };
}

app.http('feedback', {
  methods: ['POST'],
  authLevel: 'function', // não anônimo por omissão
  handler: feedbackHandler,
});
