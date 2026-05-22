import { defineConfig } from 'prisma/config';
import 'dotenv/config';

export default defineConfig({
  earlyAccess: true,
  schema: './apps/api/prisma/schema.prisma',
  datasource: {
    url: process.env.DATABASE_URL!,
  },
});
