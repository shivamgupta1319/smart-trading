import { Injectable } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { CreateSignalDto } from './dto/create-signal.dto';

@Injectable()
export class SignalsService {
  constructor(private prisma: PrismaService) {}

  async findAll() {
    return this.prisma.liveSignal.findMany({
      include: { stock: true },
      orderBy: { timestamp: 'desc' },
    });
  }

  async findActive() {
    return this.prisma.liveSignal.findMany({
      where: { status: 'ACTIVE' },
      include: { stock: true },
      orderBy: { timestamp: 'desc' },
    });
  }

  async create(dto: CreateSignalDto) {
    // Avoid duplicate active signals for same stock+strategy
    const existing = await this.prisma.liveSignal.findFirst({
      where: { stockId: dto.stockId, strategyName: dto.strategyName, status: 'ACTIVE' },
      include: { stock: true },
    });
    if (existing) return { signal: existing, isNew: false }; // idempotent

    const signal = await this.prisma.liveSignal.create({
      data: dto,
      include: { stock: true },
    });
    return { signal, isNew: true };
  }

  async close(id: number) {
    return this.prisma.liveSignal.update({
      where: { id },
      data: { status: 'CLOSED' },
    });
  }
}
