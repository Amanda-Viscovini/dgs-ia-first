import { z } from 'zod';

// Schema fechado (.strict): rejeita campos extras → evita mass assignment.
export const feedbackSchema = z
  .object({
    queryId: z.string().min(1, 'queryId é obrigatório'),
    rating: z.number().int().min(1).max(5), // faixa válida garantida
    comment: z.string().max(2000).optional(),
    attendantEmail: z.string().email(),
  })
  .strict();

export type FeedbackInput = z.infer<typeof feedbackSchema>;
