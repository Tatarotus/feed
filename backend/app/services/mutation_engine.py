import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

import httpx
from app.models import Event, Interest, SemanticMutation
from app.pipeline.enrichment.embedder import embedder
from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session, joinedload

logger = logging.getLogger("services.mutation_engine")

class MutationEngine:
    def __init__(self):
        self.endpoint = "https://dav.smre.run.place/v1/chat/completions"
        self.model = "meta/llama-3.1-70b-instruct"
        self.temperature = 0.4

    async def call_llm_for_mutations(self, parent_topic: str) -> List[str]:
        """
        Queries the custom OpenAI-compatible endpoint to generate adjacent topics.
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer none"
        }

        prompt = (
            f"You are a semantic evolution engine for a highly intellectual discovery feed.\n"
            f"Your goal is to evolve user interests by generating meaningful, high-information semantic mutations.\n"
            f"These must be adjacent topics, conceptual neighbors, or latent curiosity expansions.\n\n"
            f"CRITICAL RULES:\n"
            f"- Remain semantically close to the parent topic.\n"
            f"- Preserve intellectual coherence.\n"
            f"- Avoid mainstream algorithmic sludge, celebrity content, drama, clickbait, ragebait, and generic self-help/productivity trends.\n"
            f"- Avoid politics unless explicitly present in the topic.\n"
            f"- Generate exact, specific academic, technical, or philosophical fields/concepts.\n\n"
            f"Parent Topic: \"{parent_topic}\"\n\n"
            f"Generate exactly 5 adjacent mutations in JSON array format. Return ONLY the JSON array of strings and absolutely nothing else.\n"
            f"Example:\n"
            f"[\n"
            f"  \"adjacent field 1\",\n"
            f"  \"adjacent field 2\"\n"
            f"]"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a semantic discovery engine that generates adjacent technical and intellectual topics. Respond only in raw JSON arrays of strings."},
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature,
            "max_tokens": 200
        }

        try:
            logger.info(f"Querying meta/llama-3.1-70b-instruct for mutations of '{parent_topic}'...")
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.post(self.endpoint, json=payload, headers=headers)
                if response.status_code != 200:
                    logger.error(f"LLM endpoint returned status {response.status_code}: {response.text}")
                    return []

                res_data = response.json()
                content = res_data["choices"][0]["message"]["content"].strip()

                # Parse JSON array
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

                mutations = json.loads(content)
                if isinstance(mutations, list):
                    return [str(m).strip().lower() for m in mutations]
                return []
        except Exception as e:
            logger.error(f"Error calling LLM for mutations: {str(e)}")
            return []

    async def compute_similarity(self, v1: List[float], v2: List[float]) -> float:
        """
        Computes cosine similarity between two vectors.
        """
        dot_prod = sum(a * b for a, b in zip(v1, v2))
        norm_v1 = math.sqrt(sum(a * a for a in v1))
        norm_v2 = math.sqrt(sum(b * b for b in v2))
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
        return dot_prod / (norm_v1 * norm_v2)

    async def _evolve_first_generation(self, db: Session, interests, existing_mutations):
        for interest in interests:
            parent_topic = interest.topic
            active_count = db.scalar(
                select(func.count(SemanticMutation.id))
                .where(
                    and_(
                        SemanticMutation.parent_topic == parent_topic,
                        SemanticMutation.status != "dead"
                    )
                )
            ) or 0

            if active_count >= 5:
                continue

            raw_mutations = await self.call_llm_for_mutations(parent_topic)
            if not raw_mutations:
                continue

            parent_vector = interest.embedding
            if parent_vector is None:
                try:
                    parent_vector = await embedder.generate_embedding(parent_topic, db=db, input_type="query")
                except Exception as e:
                    logger.error(f"Failed to embed parent topic '{parent_topic}': {e}")
                    continue

            for topic in raw_mutations:
                if topic in existing_mutations or topic == parent_topic:
                    continue

                try:
                    mutation_vector = await embedder.generate_embedding(topic, db=db, input_type="query")
                    sim = await self.compute_similarity(parent_vector, mutation_vector)
                    logger.info(f"Mutation: '{topic}' -> Similarity with parent '{parent_topic}': {sim:.4f}")

                    if sim >= 0.20:
                        new_mutation = SemanticMutation(
                            parent_topic=parent_topic,
                            mutation_topic=topic,
                            parent_embedding=parent_vector,
                            mutation_embedding=mutation_vector,
                            similarity_score=sim,
                            confidence_score=0.10,
                            telemetry_score=0.0,
                            survival_score=1.0,
                            generation_depth=1,
                            status="experimental"
                        )
                        db.add(new_mutation)
                        existing_mutations.add(topic)
                        logger.info(f"Created mutation: '{topic}' (parent: '{parent_topic}') with similarity {sim:.2f}")
                    else:
                        logger.warning(f"Rejected mutation: '{topic}' due to low similarity ({sim:.2f} < 0.20)")
                except Exception as ex:
                    logger.error(f"Error generating embedding or saving mutation '{topic}': {str(ex)}")

            db.commit()

    async def _evolve_second_generation(self, db: Session, existing_mutations):
        promoted_mutations = db.scalars(
            select(SemanticMutation)
            .where(
                and_(
                    SemanticMutation.status == "promoted",
                    SemanticMutation.generation_depth == 1
                )
            )
        ).all()

        for pm in promoted_mutations:
            parent_topic = pm.mutation_topic
            parent_energy = getattr(pm, "energy", 1.0)
            if parent_energy is None:
                parent_energy = 1.0

            if parent_energy < 4.0:
                logger.info(f"Second-Gen Blocking: Parent mutation '{parent_topic}' has low energy ({parent_energy:.2f} < 4.0). Propagation blocked.")
                continue

            active_count = db.scalar(
                select(func.count(SemanticMutation.id))
                .where(
                    and_(
                        SemanticMutation.parent_topic == parent_topic,
                        SemanticMutation.status != "dead"
                    )
                )
            ) or 0

            if active_count >= 3:
                continue

            raw_mutations = await self.call_llm_for_mutations(parent_topic)
            if not raw_mutations:
                continue

            parent_vector = pm.mutation_embedding

            for topic in raw_mutations:
                if topic in existing_mutations or topic == parent_topic or topic == pm.parent_topic:
                    continue

                try:
                    mutation_vector = await embedder.generate_embedding(topic, db=db, input_type="query")
                    sim = await self.compute_similarity(parent_vector, mutation_vector)
                    logger.info(f"Second-gen Mutation: '{topic}' -> Similarity with parent '{parent_topic}': {sim:.4f}")

                    if sim >= 0.20:
                        new_mutation = SemanticMutation(
                            parent_topic=parent_topic,
                            mutation_topic=topic,
                            parent_embedding=parent_vector,
                            mutation_embedding=mutation_vector,
                            similarity_score=sim,
                            confidence_score=0.10,
                            telemetry_score=0.0,
                            survival_score=1.0,
                            generation_depth=2,
                            status="experimental",
                            energy=1.0,
                            attention_share=0.0,
                            competition_score=0.0,
                            fatigue_multiplier=1.0
                        )
                        db.add(new_mutation)
                        existing_mutations.add(topic)
                        logger.info(f"Created second-gen mutation: '{topic}' (parent: '{parent_topic}') with similarity {sim:.2f}")
                    else:
                        logger.warning(f"Rejected second-gen mutation: '{topic}' due to low similarity ({sim:.2f} < 0.20)")
                except Exception as ex:
                    logger.error(f"Error processing second-gen mutation '{topic}': {str(ex)}")

            db.commit()

    async def evolve_interests(self, db: Session):
        """
        Selects active followed interests or promoted mutations and generates first/second generation mutations.
        """
        interests = db.scalars(select(Interest)).all()
        if not interests:
            logger.info("No active interests to mutate.")
            return

        existing_mutations = {m.mutation_topic for m in db.scalars(select(SemanticMutation)).all()}
        await self._evolve_first_generation(db, interests, existing_mutations)
        await self._evolve_second_generation(db, existing_mutations)

    def _calculate_event_delta(self, event, similarity: float) -> Tuple[float, float]:
        et = event.event_type
        rating = getattr(event, "rating", None)

        delta_score = 0.0
        evt_energy = 0.0

        if et == "click":
            delta_score += 0.05
            evt_energy += 0.02
        elif et == "watch":
            watch_pct = event.watch_time_pct or 0.5
            if watch_pct >= 0.7:
                delta_score += 0.15
                evt_energy += 0.20
            elif watch_pct <= 0.1:
                delta_score -= 0.20
                evt_energy -= 0.35
            else:
                delta_score += 0.05
                evt_energy += 0.05
        elif et == "like" or rating == 1:
            delta_score += 0.25
            evt_energy += 0.25
        elif et == "subscribe":
            delta_score += 0.40
            evt_energy += 0.50
        elif et == "queue_add":
            delta_score += 0.10
            evt_energy += 0.25
        elif et in ("dislike", "disliked") or rating == -1:
            delta_score -= 0.35
            evt_energy -= 0.35
        elif et in ("skip", "dismiss"):
            delta_score -= 0.20
            evt_energy -= 0.35

        return delta_score * similarity, evt_energy * similarity

    def _accumulate_video_events(self, video_events, sim: float) -> Tuple[int, int, float, float]:
        imp_count = 0
        cli_count = 0
        m_delta = 0.0
        e_change = 0.0
        for event in video_events:
            if event.event_type == "impression":
                imp_count += 1
                continue
            if event.event_type in ("click", "watch"):
                cli_count += 1
            ds, ee = self._calculate_event_delta(event, sim)
            m_delta += ds
            e_change += ee
        return imp_count, cli_count, m_delta, e_change

    def _gather_mutation_events(self, mutation_vector, events_by_video) -> Tuple[float, float, int, int, int]:
        mutation_delta = 0.0
        energy_change = 0.0
        matched_videos_count = 0
        impression_count = 0
        click_count = 0

        for _video_id, video_events in events_by_video.items():
            video = video_events[0].video
            if not video or video.embedding is None:
                continue

            dot_product = sum(a * b for a, b in zip(video.embedding, mutation_vector))
            sim = max(float(dot_product), 0.0)

            if sim >= 0.45:
                matched_videos_count += 1
                ic, cc, md, ec = self._accumulate_video_events(video_events, sim)
                impression_count += ic
                click_count += cc
                mutation_delta += md
                energy_change += ec

        return mutation_delta, energy_change, impression_count, click_count, matched_videos_count

    def _update_mutation_fatigue_and_energy(self, mutation, energy_change, impression_count, click_count, matched_videos_count):
        if len(mutation.mutation_topic) > 0 and matched_videos_count >= 2:
            energy_change += 0.70

        if getattr(mutation, "fatigue_multiplier", None) is None:
            mutation.fatigue_multiplier = 1.0

        if impression_count > 0 and click_count == 0:
            mutation.fatigue_multiplier = max(0.10, mutation.fatigue_multiplier - 0.05 * impression_count)
        else:
            mutation.fatigue_multiplier = min(1.0, mutation.fatigue_multiplier + 0.10)

        if energy_change > 0:
            energy_change *= mutation.fatigue_multiplier

        if getattr(mutation, "energy", None) is None:
            mutation.energy = 1.0
        mutation.energy *= 0.985
        mutation.energy = max(0.0, mutation.energy + energy_change)

    def _update_mutation_scores(self, db: Session, mutation, mutation_delta):
        mutation.telemetry_score = float(mutation_delta)

        if mutation_delta > 0:
            old_conf = mutation.confidence_score
            mutation.confidence_score = max(0.01, min(1.0, old_conf + mutation_delta))

            if mutation.generation_depth == 1:
                parent_interest = db.scalar(select(Interest).where(Interest.topic == mutation.parent_topic))
                if parent_interest:
                    old_w = parent_interest.weight
                    parent_interest.weight = max(0.25, min(1.50, old_w + 0.02 * mutation.similarity_score))
                    logger.info(f"Reinforced parent topic '{mutation.parent_topic}' weight: {old_w:.2f}x -> {parent_interest.weight:.2f}x")

            if mutation.status == "experimental" and mutation.confidence_score >= 0.40:
                mutation.status = "promoted"
                logger.info(f"PROMOTED mutation '{mutation.mutation_topic}' to 'promoted' status!")
        else:
            old_conf = mutation.confidence_score
            decay_amt = -0.02 + mutation_delta
            mutation.confidence_score = max(0.0, min(1.0, old_conf + decay_amt))
            mutation.survival_score = max(0.0, mutation.survival_score - 0.05)

    def _evaluate_single_mutation(self, db: Session, mutation, events_by_video):
        mutation_vector = mutation.mutation_embedding
        if mutation_vector is None:
            return

        mutation_delta, energy_change, impression_count, click_count, matched_videos_count = self._gather_mutation_events(mutation_vector, events_by_video)
        self._update_mutation_fatigue_and_energy(mutation, energy_change, impression_count, click_count, matched_videos_count)
        self._update_mutation_scores(db, mutation, mutation_delta)

        if mutation.energy < 0.15 or mutation.confidence_score < 0.05 or mutation.survival_score <= 0.0:
            mutation.status = "dead"
            logger.info(f"Ecosystem Extinction: Mutation '{mutation.mutation_topic}' starved to death (Energy: {mutation.energy:.2f}).")
        else:
            logger.info(f"Processed mutation '{mutation.mutation_topic}': energy={mutation.energy:.2f}, conf={mutation.confidence_score:.2f}, fatigue_multiplier={mutation.fatigue_multiplier:.2f}, status={mutation.status}")

    def _process_sibling_competition(self, active_mutations):
        cluster_groups = {}
        for m in active_mutations:
            if m.status == "dead":
                continue
            parent = m.parent_topic
            if parent not in cluster_groups:
                cluster_groups[parent] = []
            cluster_groups[parent].append(m)

        for parent, muts in cluster_groups.items():
            if len(muts) > 4:
                logger.warning(f"Cognitive Immune System: Topic monoculture detected in cluster '{parent}' ({len(muts)} mutations). Suppressing energy & confidence...")
                for m in muts:
                    m.energy *= 0.80
                    m.confidence_score = max(0.01, m.confidence_score * 0.85)

            total_cluster_energy = sum(m.energy for m in muts)
            if total_cluster_energy > 0:
                for m in muts:
                    raw_share = m.energy / total_cluster_energy
                    m.attention_share = min(0.35, raw_share)
            else:
                for m in muts:
                    m.attention_share = 0.0

            muts.sort(key=lambda x: x.energy, reverse=True)
            for idx, m in enumerate(muts):
                m.competition_score = float(idx + 1)

    def _enforce_global_budget_and_prune(self, db: Session, active_mutations):
        total_system_energy = sum(m.energy for m in active_mutations if m.status != "dead")
        if total_system_energy > 100.0:
            scale_factor = 100.0 / total_system_energy
            logger.info(f"Global Resource budget exceeded ({total_system_energy:.1f} > 100.0). Scaling down by {scale_factor:.3f}...")
            for m in active_mutations:
                if m.status != "dead":
                    m.energy *= scale_factor

        db.execute(delete(SemanticMutation).where(SemanticMutation.status == "dead"))
        db.commit()

    def process_telemetry(self, db: Session):
        """
        Sweeps active mutations, queries user events on related videos in the last 24h,
        and runs the state machine to reinforce/decay/promote/kill mutations.
        """
        logger.info("Evaluating mutation telemetry scores and processing ecosystem state machine...")

        active_mutations = db.scalars(
            select(SemanticMutation).where(SemanticMutation.status != "dead")
        ).all()

        if not active_mutations:
            logger.info("No active mutations to evaluate telemetry for.")
            return

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        events = db.scalars(
            select(Event)
            .options(joinedload(Event.video))
            .where(Event.created_at >= cutoff)
        ).all()

        events_by_video = {}
        for event in events:
            if event.video_id not in events_by_video:
                events_by_video[event.video_id] = []
            events_by_video[event.video_id].append(event)

        for mutation in active_mutations:
            self._evaluate_single_mutation(db, mutation, events_by_video)

        self._process_sibling_competition(active_mutations)
        self._enforce_global_budget_and_prune(db, active_mutations)

# Expose global service instance
mutation_engine = MutationEngine()
