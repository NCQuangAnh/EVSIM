import type { Pt } from "./geom";

export interface Road {
  pts: Pt[];
  cls: string;
  link: boolean;
  lanes: number;
  oneway: boolean;
  rb: boolean; // part of a roundabout
  name: string;
}

/** [from node, to node, road index, 1 if travelling along road.pts else 0, length m] */
export type Edge = [number, number, number, number, number];

export interface MapData {
  meta: { name: string; size: Pt; attribution: string };
  boundary: Pt[][];
  roads: Road[];
  nodes: Pt[];
  edges: Edge[];
  vin: { rings: Pt[][]; cat: string; name: string }[];
  blocks: { rings: Pt[][]; kind: string }[];
  labels: { name: string; at: Pt; cat: string }[];
  zones: { name: string; at: Pt }[];
  green: { rings: Pt[][]; kind: string }[];
  water: { rings: Pt[][] }[];
  stations: { at: Pt; src: string; ports: number | null }[];
  /** traffic light controllers: junction nodes they control, from OSM or assumed */
  signals: { nodes: number[]; at: Pt; src: "osm" | "assumed" }[];
}
