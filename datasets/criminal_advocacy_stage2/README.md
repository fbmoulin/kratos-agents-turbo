# Criminal Advocacy Stage 2 Dataset

Primeiro corpus realista e anonimizado para validar o fluxo canônico de advocacia criminal sem alterar o backend ou o runtime.

## Estrutura

```text
datasets/criminal_advocacy_stage2/
├── manifest.json
├── resposta_a_acusacao/
├── revogacao_prisao_preventiva/
├── habeas_corpus/
└── alegacoes_finais/
```

## Contrato de cada caso

Cada arquivo JSON contém:

- `raw_case_text`: narrativa principal do caso, em linguagem próxima do processo.
- `raw_case_context`: contexto adicional opcional para intake e priorização.
- `target_piece_type`: peça esperada.
- `expected_strategic_direction`: direção estratégica defensiva esperada.
- `notes.risks`: riscos processuais ou narrativos.
- `notes.proof_gaps`: lacunas de prova relevantes.
- `notes.tactical_priorities`: prioridades táticas para a defesa.
- `canonical_advocacy_pipeline`: mapeamento explícito para `detector -> firac -> validator`.

## Alinhamento com o pipeline canônico

- `detector`: usa `raw_case_text` e `raw_case_context` para inferir fase, urgência e tipo de peça.
- `firac`: usa `expected_strategic_direction` para orientar tese defensiva, framing dos fatos e pedidos.
- `validator`: usa `notes` para checar riscos, contradições, lacunas probatórias e aderência tática.

## Escopo

- 10 casos criminais sintéticos, porém realistas.
- Todos os dados são anonimizados e não contêm identificadores reais.
- O dataset é aditivo: serve como base para testes end-to-end e avaliação qualitativa, sem mudar contratos públicos do runtime atual.
