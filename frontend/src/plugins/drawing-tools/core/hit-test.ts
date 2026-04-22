import { PixelPoint } from './types';

export const HitTestUtils = {
  pointToPointDistance(p1: PixelPoint, p2: PixelPoint): number {
    return Math.sqrt(Math.pow(p1.x - p2.x, 2) + Math.pow(p1.y - p2.y, 2));
  },

  pointToSegmentDistance(p: PixelPoint, a: PixelPoint, b: PixelPoint): number {
    const l2 = Math.pow(a.x - b.x, 2) + Math.pow(a.y - b.y, 2);
    if (l2 === 0) return this.pointToPointDistance(p, a);
    let t = ((p.x - a.x) * (b.x - a.x) + (p.y - a.y) * (b.y - a.y)) / l2;
    t = Math.max(0, Math.min(1, t));
    const proj = { x: a.x + t * (b.x - a.x), y: a.y + t * (b.y - a.y) };
    return this.pointToPointDistance(p, proj);
  },

  isPointInRect(p: PixelPoint, topLeft: PixelPoint, bottomRight: PixelPoint): boolean {
    const minX = Math.min(topLeft.x, bottomRight.x);
    const maxX = Math.max(topLeft.x, bottomRight.x);
    const minY = Math.min(topLeft.y, bottomRight.y);
    const maxY = Math.max(topLeft.y, bottomRight.y);
    return p.x >= minX && p.x <= maxX && p.y >= minY && p.y <= maxY;
  },

  pointToHorizontalLineDistance(p: PixelPoint, lineY: number): number {
    return Math.abs(p.y - lineY);
  },

  pointToHorizontalRayDistance(
    p: PixelPoint,
    origin: PixelPoint,
    direction: 'left' | 'right',
  ): number {
    const isWithinRay = direction === 'right' ? p.x >= origin.x : p.x <= origin.x;
    if (!isWithinRay) {
      // 鼠标在射线起点的另一侧，计算鼠标到起点的距离
      return this.pointToPointDistance(p, origin);
    }
    // 鼠标在射线同侧，只需计算 Y 轴距离
    return Math.abs(p.y - origin.y);
  }
};
