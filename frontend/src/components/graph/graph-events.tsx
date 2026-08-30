"use client";

import { useRegisterEvents, useSigma } from "@react-sigma/core";
import { useEffect, useRef } from "react";

interface Props {
  onHoverNode: (nodeId: string | null) => void;
  onSelectNode: (nodeId: string | null) => void;
  onSelectEdge: (edgeId: string | null) => void;
  onExpandNode: (nodeId: string) => void;
}

export function GraphEvents({ onHoverNode, onSelectNode, onSelectEdge, onExpandNode }: Props) {
  const sigma = useSigma();
  const registerEvents = useRegisterEvents();
  const draggedNode = useRef<string | null>(null);

  useEffect(() => {
    registerEvents({
      enterNode: ({ node }) => onHoverNode(node),
      leaveNode: () => onHoverNode(null),
      clickNode: ({ node }) => {
        onSelectEdge(null);
        onSelectNode(node);
      },
      doubleClickNode: ({ node, event }) => {
        event.preventSigmaDefault();
        onExpandNode(node);
      },
      clickEdge: ({ edge }) => {
        onSelectNode(null);
        onSelectEdge(edge);
      },
      clickStage: () => {
        onSelectNode(null);
        onSelectEdge(null);
      },
      downNode: ({ node, event }) => {
        draggedNode.current = node;
        sigma.getGraph().setNodeAttribute(node, "highlighted", true);
        sigma.getCamera().disable();
        event.preventSigmaDefault();
      },
      mousemovebody: (event) => {
        if (!draggedNode.current) return;
        const position = sigma.viewportToGraph(event);
        sigma.getGraph().mergeNodeAttributes(draggedNode.current, position);
        event.preventSigmaDefault();
        event.original.preventDefault();
      },
      mouseup: () => {
        if (draggedNode.current) {
          sigma.getGraph().removeNodeAttribute(draggedNode.current, "highlighted");
          draggedNode.current = null;
        }
        sigma.getCamera().enable();
      },
    });
  }, [onExpandNode, onHoverNode, onSelectEdge, onSelectNode, registerEvents, sigma]);

  return null;
}
