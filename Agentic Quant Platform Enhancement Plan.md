# **Architectural Analysis and Enhancement Blueprint for an Agentic Quantitative Trading Platform**

## **Executive Overview of the Paradigm Shift in Quantitative Systems**

The intersection of quantitative finance and large language models represents a fundamental paradigm shift in algorithmic trading architecture. Historically, quantitative platforms have relied on deterministic, human-coded logic executed within rigid, high-performance environments. The emergence of agentic workflows introduces non-deterministic reasoning engines capable of parsing unstructured data, generating dynamic code, and adapting to novel market microstructures. However, integrating autonomous agents into regulated, risk-sensitive financial environments requires an architecture that enforces strict boundaries between probabilistic reasoning and deterministic execution. Forecasts suggest that artificial intelligence strategies will drive approximately eighty-nine percent of global trading volume by the year 2025, transforming algorithmic intelligence from a specialist tool into the baseline market standard.1 Trades will settle faster, spreads will tighten, and positions will rebalance in seconds, necessitating systems that can process millions of events without catastrophic failure.1

The analysis indicates that the target system, the agentic\_quant\_platform, requires a comprehensive architectural overhaul to graduate from a conceptual research repository into an institutional-grade framework. By benchmarking against industry-leading frameworks such as the QuantConnect Lean engine, a definitive blueprint emerges. The Lean engine demonstrates that professional-caliber platforms must be inherently modular, event-driven, and strictly segregated into distinct operational domains.2 Conversely, successful agentic implementations in live financial environments adhere to repeatable design patterns that prioritize tool usage over raw reasoning, mandate strict memory design for reliability, and treat risk guardrails as first-class citizens.5

This report delivers an exhaustive architectural analysis and a precise enhancement plan designed to structure internal data representations, optimize code extensibility, and establish robust project-scoped cloud governance. The following specifications are formulated to be ingested by a downstream language model to generate specific, actionable engineering tasks, thereby transforming the foundational agentic platform into an institutional-grade quantitative research and execution system capable of operating autonomously in live financial markets.

## **Core Architectural Redesign: The Event-Driven Deterministic Engine**

To successfully integrate agentic capabilities, the core trading engine must operate as a deterministic sandbox that strictly controls the outputs of the language models. The overarching philosophy must adopt a separation of concerns, ensuring that individual components are isolated and their responsibilities do not overlap.3

### **The Transition from Vectorized to Event-Driven Processing**

Traditional quantitative backtesting systems often employ vectorized processing, where operations are applied across entire arrays of historical data simultaneously. While vectorized engines utilizing libraries like Pandas or NumPy offer rapid execution during the research phase, they suffer from a fundamental flaw when applied to real-world trading simulations: the propensity for look-ahead bias.6 Vectorized systems process data at rest, whereas live markets produce data in motion.

To replicate the realities of live market conditions, the platform must transition to an event-driven architecture. In an event-driven system, market data updates, order fills, and system alerts are encapsulated as discrete events and processed sequentially through a central event queue, mimicking the chronological flow of real time.7 This guarantees that the algorithmic logic, whether driven by human code or an autonomous agent, only has access to information available up to the current time frontier.6

The event-driven paradigm operates analogously to a continuous loop, frequently compared to the event loops found in video game engines, where the system perpetually awaits the next event, identifies its type, and triggers the corresponding handler function before updating the system state.9 This architecture is particularly well-suited for high-performance, low-latency trading platforms because it removes non-deterministic behavior and allows for the precise simulation of market friction, partial fills, and sequential order routing.10

| Architectural Paradigm | Processing Methodology | Primary Advantages | Critical Vulnerabilities | Ideal Application Stage |
| :---- | :---- | :---- | :---- | :---- |
| **Vectorized Processing** | Matrix operations applied simultaneously across full time-series arrays. | Extreme computational speed; rapid hypothesis testing. | Highly susceptible to look-ahead bias; cannot accurately model slippage or partial fills. | Initial alpha screening and broad universe filtering.10 |
| **Event-Driven Processing** | Sequential evaluation of temporal events (ticks, quotes, fills) via a central queue. | High-fidelity simulation of live trading; exact replication of market microstructure. | High computational overhead; complex state management and slower backtest execution. | Final validation, execution logic modeling, and live deployment.10 |

### **Modular Framework Abstractions and the Five-Stage Pipeline**

Drawing upon the proven design patterns of the QuantConnect Lean framework, the agentic platform must implement a five-stage algorithmic pipeline. This layered abstraction allows quantitative researchers and autonomous agents to design models independently while maintaining end-to-end systemic coherence.12 The framework operates through a linear flow of data where the output of one module serves as the exact input for the next in a strictly defined sequence.3

The first stage is the Universe Selection Model, which dynamically determines the subset of assets the algorithm will monitor. This module adjusts the active trading universe based on corporate actions, liquidity changes, or macroeconomic signals, ensuring that the computational resources of the agentic layer are focused only on highly relevant securities.3

The second stage is the Alpha Generation Engine, representing the core reasoning layer where the agentic models operate. Instead of placing direct market orders—a practice that introduces unacceptable risk when utilizing probabilistic language models—this layer is restricted to generating abstract "Insight" objects.3 An Insight indicates the predicted direction, expected magnitude, statistical confidence, and anticipated time horizon of a market movement.3

The third stage, the Portfolio Construction Model, ingests these Insights from single or multiple concurrent agents and determines the target position sizes. It outputs optimized portfolio targets, balancing the confidence of the agentic predictions against the holistic requirements of modern portfolio theory or proprietary allocation algorithms.3

The fourth stage involves the Risk Management Model. Operating as an absolute constraint layer, this module intercepts the portfolio targets and applies hard-coded quantitative boundaries. It adjusts or cancels targets to ensure the system remains within predefined drawdown limits, sector exposure caps, and volatility thresholds.3

The final stage is the Execution Model, the deterministic layer that translates risk-adjusted targets into optimized broker orders. This component accounts for order book depth and latency, utilizing algorithms such as volume-weighted average price to minimize market impact.3

By forcing the language model to operate exclusively within the Alpha Generation layer—emitting standardized insights rather than direct orders—the architecture completely neutralizes the risk of a hallucinated, catastrophic trade execution. The deterministic Risk and Portfolio layers act as an impenetrable firewall against non-deterministic anomalies.

## **High-Performance Internal Data Representations**

The efficacy of a quantitative platform is heavily dependent on the memory efficiency and processing speed of its internal data representations. The transition from low-frequency daily modeling to high-frequency intraday and tick-level analysis necessitates a departure from legacy data structures. As datasets expand into the terabyte scale, inefficient memory allocation results in severe processing bottlenecks that cripple the iterative research cycle.

### **The Shift to Columnar Memory Formats and Rust Execution**

Historically, the Python quantitative ecosystem has relied extensively on the Pandas library for tabular data processing.13 While Pandas provides exceptional versatility for data manipulation, its underlying architecture—built atop NumPy—suffers from significant limitations regarding memory representation, the global interpreter lock, and multi-threaded operations.15 When processing gigabyte-scale datasets consisting of millions of market ticks, Pandas frequently encounters memory bloat and performance degradation.

The enhancement plan mandates the integration of Apache Arrow and Polars as the foundational data structures for the platform. Apache Arrow provides a cross-language, standardized columnar memory format that specifies an exact memory layout for analytical operations.16 By utilizing a columnar format, contiguous memory addresses store identical data types, allowing modern central processing units to leverage single-instruction, multiple-data (SIMD) operations. Furthermore, Arrow eliminates the massive serialization and deserialization overhead typically incurred when passing data between the Python-based agentic layers and the underlying high-performance C++ or Rust execution engines.16

Polars, built entirely on Rust and utilizing the Arrow memory model, enables blazingly fast, multi-threaded query execution.16 It employs a lazy evaluation engine that optimizes query plans before execution, drastically reducing memory overhead. By implementing Polars dataframes, the platform ensures cache-coherent algorithms and minimizes memory footprints, which is critical when language models are conducting expansive historical context retrievals during live trading simulations. The speed enhancements—often ranging from ten to fifty times faster than traditional libraries—directly translate to reduced cloud computing costs and vastly accelerated research cycles.14

### **Structuring OHLCV and Tick Data Pipelines**

The platform must maintain distinct, strictly typed internal representations for aggregated bar data and raw tick data, as each serves a fundamentally different quantitative purpose within the agentic workflow.

Open, High, Low, Close, Volume (OHLCV) data represents a compressed narrative of market activity over a fixed temporal interval.19 It is highly efficient for pattern recognition, long-range strategy visualization, and serving as the primary context window for training language models on macroeconomic trends.19 Because OHLCV data is relatively small and lightweight, it is ideal for strategies that do not rely on market microstructure.19

In contrast, tick data records every individual trade and quote update with microsecond or nanosecond precision, capturing the raw, unaggregated market reality.19 Tick data is indispensable for slippage modeling, latency simulation, order flow analysis, and the training of high-frequency execution algorithms.19 However, managing tick data introduces massive storage and processing requirements, with active instruments generating millions of rows per day, requiring specialized time-series databases like ClickHouse or highly compressed Parquet files stored on NVMe arrays.23

The system must define precise schemas for these data types to ensure consistent processing across the event-driven pipeline.

| Data Representation Type | Analytical Purpose and Target Use Case | Required Memory Format | Core Schema Attributes |
| :---- | :---- | :---- | :---- |
| **Tick Trade Event** | Execution modeling, slippage simulation, transaction cost analysis.19 | Arrow RecordBatch (Int64/Float64) | timestamp (ns), symbol\_id, price, size, trade\_id, taker\_side.19 |
| **Tick Quote Event** | Spread analysis, market depth assessment, bid-ask dynamics.22 | Arrow RecordBatch (Int64/Float64) | timestamp (ns), symbol\_id, bid\_price, bid\_size, ask\_price, ask\_size |
| **OHLCV Time Bar** | Agentic context generation, technical indicators, charting visualization.19 | Polars DataFrame (Columnar) | start\_time, end\_time, symbol\_id, open, high, low, close, volume.19 |
| **Limit Order Book (LOB) Vector** | Microstructure prediction, neural network state representation.24 | SequenceSample Tensor (![][image1]) | A ![][image2]\-vector encoding prices and volumes on both sides of the book to depth ![][image3].24 |

When the platform processes live tick data, it must dynamically aggregate these ticks into OHLCV representations in real-time. This can be achieved using highly efficient object-oriented data structures such as a customized TickByTick accumulator class or by utilizing TimescaleDB continuous aggregates.25 This dual-track pipeline ensures that execution handlers receive raw ticks for simulated market friction, while the agentic reasoning models simultaneously receive the latest aggregated bars without waiting for a temporal window to close, facilitating immediate decision-making capabilities.

## **Enhancing Quantitative Finance and Execution Models**

To transition the platform from a theoretical framework to a production-ready trading system, the enhancement plan mandates the rigorous integration of advanced quantitative elements. This involves upgrading the mathematical rigor of the risk frameworks, refining the execution latency simulators, and adapting optimization methodologies to suit non-deterministic language models.

### **Advanced Risk Management and Tail Event Protection**

The platform must support sophisticated, layered risk models that operate entirely independent of the alpha-generating agents. These models must continuously monitor the portfolio target collections and dynamically intercept orders that violate systemic thresholds.3

A fundamental requirement is the implementation of a Trailing Stop Risk Management Model. This model tracks the peak-to-trough drawdown of unrealized profit for every individual security in the portfolio. If a position reverses significantly from its highest point of unrealized profit and breaches a predefined percentage threshold, the model automatically overrides the agentic insight, generates a liquidation target, and cancels all associated active signals.3 This mechanism secures gains and limits losses systematically, removing the emotional or algorithmic hesitation inherent in strategy exit logic.

Furthermore, the system requires the implementation of advanced statistical risk metrics to manage extreme market conditions, such as the Tail Value at Risk (TVaR) model. While standard Value at Risk evaluates the maximum loss within a specific confidence interval, TVaR calculates the expected severity of the loss in the worst-case scenarios that fall beyond that interval. The mathematical formulation for TVaR based on log-normal returns is expressed as:

![][image4]  
In this equation, ![][image5] represents the mean return, ![][image6] denotes the standard deviation, ![][image7] signifies the confidence level, ![][image8] is the standard normal probability density function, and ![][image9] is the inverse cumulative distribution function.3 If the portfolio's unrealized profit breaches the calculated TVaR threshold, the risk module preemptively liquidates the exposed assets, ensuring the platform survives catastrophic market tail events such as flash crashes.3 Additional modular risk implementations should include sector exposure management to enforce diversification and option hedging models to mathematically offset large directional equity exposures.3

### **Microstructure Simulation and Low-Latency Execution Realism**

A primary failure point in nascent algorithmic platforms is the assumption of perfect execution. The backtesting engine must incorporate high-fidelity simulation of market friction.8

The execution handler must model the bid-ask spread accurately, utilizing historical tick data to determine the exact cost of crossing the spread at any given microsecond.7 Furthermore, the engine must simulate market depth and liquidity constraints. If an agentic strategy attempts to offload a position size that exceeds the available historical volume at the best bid, the execution model must simulate partial fills and calculate the subsequent slippage as the order progressively consumes liquidity deeper into the order book.10

To mitigate these simulated costs, the extensible architecture must support the implementation of advanced execution algorithms. For instance, an Iceberg Execution Model can be plugged into the engine to handle large portfolio targets. Instead of routing a massive market order that would immediately erode profit margins via slippage, the iceberg model mathematically slices the total target volume. It executes only a marginal, predefined percentage of the currently available order book volume, obscuring the algorithm's trading footprint from high-frequency predatory models.3 Additionally, Favorable Price Execution models can be deployed to restrict order placement to milliseconds when the current market price is statistically superior to the price at the time the original insight was generated, further optimizing the entry mechanics.3

For institutions targeting the high-frequency domain, the platform's execution logic must be aware of hardware-level network optimizations. Modern high-frequency systems bypass the standard operating system network stack using the Data Plane Development Kit (DPDK) and Remote Direct Memory Access (RDMA), reducing data ingestion latency from fifty microseconds down to a mere one to five microseconds.29 Incorporating logic that simulates these nanosecond-level advantages allows the platform to accurately test arbitrage and market-making strategies that rely on spatial and temporal precision.

### **Optimization Methodologies for Neural Adaptation**

The integration of agentic models requires a reevaluation of how the platform optimizes strategies. Traditional gradient-based methods, powered by backpropagation, dominate standard machine learning.30 However, these methods are computationally exhaustive and biologically implausible, struggling with scalability in highly dynamic, high-dimensional financial settings.30

The platform must integrate support for derivative-free, or zeroth-order (ZO), optimization techniques. These approaches approximate gradients and achieve competitive performance by relying solely on function evaluations and randomness, making them exceptionally relevant for adapting internal data representations within autonomous agents operating in live markets.30 Recognizing the implicit bias of stochastic gradient descent allows the system to identify the precise moment an overparameterized model shifts from merely interpolating training data to actually finding a generalizable solution, a phenomenon known as grokking.30 Providing tools to measure and trigger this delayed generalization is critical for maintaining robust agentic reasoning.

## **Designing for Extensibility and Agentic Orchestration**

To ensure long-term viability, the enhancement plan prioritizes an architecture where future capabilities can be added without modifying the core engine's source code, adhering strictly to the Open-Closed Principle of software engineering.32 Extensibility in an agentic platform is not merely about adding new financial indicators; it requires standardizing how non-human agents interact with the deterministic trading environment.

### **The Plugin Architecture and Dependency Management**

The platform will implement a robust plugin architecture where every critical component—data ingestion, analytical indicators, risk models, and broker execution—is abstracted behind formal interface contracts. When a quantitative researcher or an autonomous agent wishes to introduce a new behavior, they create a discrete new file containing a handler class that implements the interface. This component is then registered at system startup via an inversion-of-control container or a unified configuration file, adding capabilities without risking the integrity of the core execution loop.33

For legacy quantitative libraries written in C or C++, the platform should leverage ISO C++ standard parallelism. This allows developers to replace serial loops with standard parallel algorithms, instantly modernizing the codebase to utilize GPU and CPU parallelism without extensive rewrites, thereby accelerating mathematical, statistical, and pricing models while maintaining strict regulatory compliance.34 Furthermore, robust dependency management must be enforced. If a specific downstream strategy depends on the output of an upstream feature-engineering pipeline, the orchestration layer must model that relationship explicitly, utilizing sensors or triggers to wait for data arrival rather than relying on brittle, time-based execution schedules.35

### **Tool Usage and the Model Context Protocol**

Analysis of dominant agentic design patterns indicates that raw reasoning by language models is insufficient for rigorous financial environments.5 Language models excel at semantic analysis, sentiment extraction, and code generation, but they lack the deterministic precision required for complex mathematical computation and state management.36 Therefore, the platform must expose its extensible functions to the agents strictly as programmatic tools.

The implementation will utilize modern connector standards, such as the open-source Model Context Protocol (MCP), to expose the platform's API to the agents.37 The agents will interact with the system by invoking specifically scoped tools rather than generating direct state-change commands. The architecture forces the agent to rely on the engine's deterministic math libraries—such as SciPy for optimization and curve fitting, or Statsmodels for stationarity tests and cointegration calculations—rather than attempting to calculate portfolio variance or moving averages internally.14

### **Multi-Agent Orchestration Frameworks**

The monolithic agent paradigm is inadequate for complex quantitative workflows. Production systems operating in regulated environments typically separate duties into repeatable multi-agent architectural patterns.5 The platform must provide the scaffolding to orchestrate multiple, specialized sub-agents operating concurrently.5

The primary configuration involves a hierarchical Multi-Agent System (MAS). A Market Monitoring Agent continuously analyzes incoming OHLCV data and macroeconomic news feeds, identifying semantic shifts and momentum anomalies. Upon detecting an opportunity, it triggers a Quant Agent, which formulates a trading hypothesis and utilizes code-generation capabilities to draft an Alpha model script. Simultaneously, a Risk Simulation Sub-Agent executes Monte Carlo scenarios against the proposed Alpha model to assess potential drawdown exposure across thousands of simulated market paths.5

| Specialized Agent Role | Architectural Pattern | Primary Responsibility | Associated MCP Tool Access |
| :---- | :---- | :---- | :---- |
| **Market Monitor** | Trading Bot (Controlled Autonomy) | Parses live data streams and news feeds to identify momentum and regime shifts.5 | get\_latest\_ohlcv(), fetch\_sentiment\_scores() |
| **Quant Generator** | Trading Bot (Controlled Autonomy) | Formulates hypotheses and generates the logic for the Alpha Generation Engine.5 | validate\_syntax(), run\_local\_backtest() |
| **Risk Simulator** | Risk Analytics (Continuous Loop) | Evaluates the proposed strategy against extreme historical scenarios and TVaR thresholds.5 | execute\_monte\_carlo(), query\_margin\_limits() |
| **Compliance Auditor** | Compliance Assistant (Audit-First) | Monitors transaction ledgers, flags anomalies, and generates structured compliance logs.5 | read\_event\_ledger(), generate\_audit\_report() |

Only if all specialized agents achieve a consensus that satisfies the hard-coded systemic parameters does the overarching orchestration layer permit the strategy to enter the live execution pipeline. This compartmentalization ensures that failures in logic are isolated and caught by dedicated adversarial agents.

## **Project-Scoped Tagging and FinOps Cloud Governance**

Quantitative research platforms generate immense computational overhead. The processes of backtesting across decades of high-resolution tick data, conducting hyperparameter optimizations, and continuously inferencing large language models demand extensive, scalable cloud infrastructure. Without stringent governance, the financial cost of operating the platform rapidly becomes unsustainable. The implementation of robust, project-scoped resource tagging is an absolute necessity for cloud optimization and Financial Operations (FinOps) integration.38

### **The Necessity of Cloud Resource Tagging**

Cloud tags are metadata labels consisting of key-value pairs assigned to infrastructure resources such as virtual machines, storage buckets, and containerized workloads.40 In the context of the agentic platform, tagging serves as the connective tissue between the engineering architecture and the financial business outcomes. Consistent tagging provides actionable visibility, allowing financial operations teams to correlate specific cloud expenditures directly to individual research projects, specific autonomous agents, or discrete backtesting simulation runs.38

When resources are accurately tagged, the organization can track cost allocation, forecast future budgetary requirements, and conduct return on investment (ROI) calculations for specific algorithmic strategies.43 If a particular agentic optimization loop consumes computational resources that outweigh the projected alpha generation of the resulting strategy, the tagging infrastructure enables the immediate identification and termination of that specific workload. Accurate tagging powers internal showback and chargeback reports, ensuring all departments maintain visibility and take ownership of their cloud management decisions.44

### **Developing the Tagging Taxonomy**

A successful tagging strategy demands a strictly standardized vocabulary and taxonomy. Unrestricted tagging leads to spelling variations, casing discrepancies, and fragmented reporting.41 The platform infrastructure must enforce a predefined set of mandatory tags across all deployed resources. A best practice is to start with a small, required set of four to six mandatory tags to deliver real value without slowing down engineering delivery speeds.46

| Mandatory Tag Key | Purpose and Financial Operations Alignment | Allowable Values (Example) |
| :---- | :---- | :---- |
| Environment | Distinguishes between research, testing, and live execution infrastructure to prevent accidental overlaps.46 | research, backtest, staging, production |
| Project | Links compute costs to specific quantitative strategies or agent workflows.46 | alpha\_momentum\_v1, llm\_sentiment\_engine |
| CostCenter | Maps infrastructure to organizational accounting systems for automated chargeback reporting.46 | quant\_research\_01, execution\_ops\_02 |
| Owner | Identifies the specific engineer, researcher, or agent responsible for the operational workload.46 | agent\_coordinator, j\_doe, system\_orchestrator |
| DataClassification | Assures compliance by tracking the regulatory sensitivity of the data being processed by the resource.46 | public\_market\_data, proprietary\_alpha, regulated\_pii |

By maintaining a strict schema, the organization ensures that the tagging framework provides maximum value. Policies must dictate that keys behave as case-insensitive while values remain case-sensitive, utilizing consistent separators and avoiding whitespace to ensure compatibility with downstream automation tools.45

### **Automation and Infrastructure as Code**

The enforcement of the tagging policy cannot rely on manual compliance. To avoid untagged resources, the platform must embed the required tags directly into its Infrastructure as Code (IaC) files, utilizing tools like Terraform modules or AWS CloudFormation templates.44 Whenever the platform spins up an ephemeral Kubernetes pod to execute a distributed backtest, or provisions an S3 bucket to store downloaded fundamental data, the continuous integration and continuous deployment (CI/CD) pipelines must automatically inject the project-scoped tags.44

To maintain continuous governance, the architecture must integrate with cloud-native compliance tools, such as Azure Policy or AWS Tag Policies, to actively deny the provisioning of any resource that lacks the mandatory tagging schema.43 Furthermore, automated remediation scripts should routinely scan the environment, utilizing cloud-native scanners to flag invalid or untagged resources and automatically correct them or trigger infrastructure cleanup workflows, preventing the accumulation of costly, orphaned cloud instances.38

## **Implementation Blueprint for Downstream LLM Expansion**

The following structured blueprint is explicitly formatted to serve as the master context for a downstream large language model. The LLM is expected to parse these architectural directives and autonomously generate the requisite epics, ticket descriptions, API interface definitions, and core boilerplate code necessary to execute the enhancement plan.

### **Phase 1: Data Layer Optimization and Memory Architecture**

The foundation of the platform must be refactored to support high-performance, vectorized computation and deterministic state reconstruction.

**Action Item 1.1: Polars and Arrow Migration**

The downstream LLM must generate migration scripts to remove legacy Pandas dependencies within the data ingestion and transformation pipelines. The LLM will write data loader classes that fetch raw tick and OHLCV CSV/Parquet files and instantiate them exclusively as Apache Arrow RecordBatches and Polars DataFrames. The LLM must construct a memory manager class that handles the zero-copy sharing of these Arrow structures between the data ingestion microservice and the strategy execution engine.

**Action Item 1.2: Tick-to-Bar Aggregation Engine**

The LLM is tasked with writing a real-time TickByTick streaming aggregator class. This component must accept an asynchronous stream of Level 1 tick data (price, size, timestamp) and dynamically construct perfectly synchronized OHLCV bars based on customizable temporal or volume-based parameters. The code must include logic to handle late-arriving ticks and out-of-order execution scenarios, ensuring the chronological integrity of the data stream for the event queue.

**Action Item 1.3: Event-Sourced Portfolio Ledger**

The LLM must design an immutable portfolio state tracker utilizing the event sourcing pattern. Every transaction, commission deduction, and slippage application must be coded as an append-only event object. The LLM will provide the implementation for a state-reconstruction method that allows any agent or compliance auditor to query the exact margin, exposure, and cash balance of the portfolio at any specified nanosecond in trading history.

### **Phase 2: The Event-Driven Deterministic Sandbox**

The core loop must be isolated to guarantee that agentic reasoning cannot bypass systemic market constraints or introduce look-ahead bias.

**Action Item 2.1: Central Event Bus Implementation**

The LLM will implement a high-performance event loop utilizing Python's collections.deque for maximum append and pop-left execution speed. The LLM must define the abstract base classes for MarketEvent, SignalEvent, OrderEvent, and FillEvent. All subsequent modules must be refactored to communicate exclusively by placing and consuming these strictly typed objects from the central queue, abandoning direct method calls between unassociated modules.

**Action Item 2.2: Modular Interface Contracts**

The LLM must write the abstract base classes that enforce the Open-Closed Principle across the five-stage pipeline. This includes defining the IAlphaModel, IPortfolioConstructionModel, IRiskManagementModel, and IExecutionModel interfaces. The LLM must explicitly define the input parameters (e.g., historical data slices) and the required return types (e.g., standard Insight objects or PortfolioTarget collections) for each interface, mimicking the structural rigor of the QuantConnect Lean architecture.

**Action Item 2.3: Market Friction Simulator**

The LLM is directed to build the ExecutionHandler module responsible for simulating realistic trading conditions during backtesting. The LLM will implement algorithms that calculate dynamic slippage based on trade size versus historical candle volume. Furthermore, it must draft classes to assess fixed and tiered commission structures based on standard institutional brokerage fee schedules.

### **Phase 3: Agentic Orchestration and Integration**

The platform must safely harness the language model's capabilities by treating it as a restricted module that invokes pre-defined tools rather than acting as a monolithic controller.

**Action Item 3.1: Model Context Protocol (MCP) Tooling**

The LLM will design a suite of MCP-compliant tools that expose the deterministic engine's mathematical and data capabilities to the agentic layer. The LLM must generate JSON Schema definitions for tools such as get\_historical\_volatility(symbol, period), query\_portfolio\_margin(), and simulate\_insight\_impact(insight\_object). The prompt engineering structure must be written to force the agent to utilize these tools to formulate decisions rather than relying on its internal, frozen weight context.

**Action Item 3.2: Multi-Agent Hierarchy**

The LLM must draft the orchestration logic for the Multi-Agent System. This includes the state machine definition that connects a Market Monitoring agent, a Quant Generation agent, and a Risk Evaluation agent. The LLM will write the consensus protocol that dictates how the orchestrator evaluates the outputs of these sub-agents before translating their combined reasoning into a formalized SignalEvent.

**Action Item 3.3: The Alpha Generation Wrapper**

The LLM will implement the specific wrapper class that encapsulates the agentic workflow within the IAlphaModel interface. This wrapper guarantees that regardless of the complexity of the agent's internal monologue or natural language generation, the final output to the system is strictly limited to an array of standardized Insight objects that the deterministic portfolio and risk layers can securely process.

### **Phase 4: Cloud Infrastructure and FinOps Tagging**

To support institutional scale, the LLM must generate the infrastructure deployment code that strictly enforces the defined resource governance policies.

**Action Item 4.1: IaC Tagging Implementation**

The LLM must generate Terraform configuration files for provisioning the requisite cloud resources, including compute clusters for backtesting, blob storage for financial data, and serverless functions for event routing. The LLM will hardcode the mandatory Environment, Project, CostCenter, Owner, and DataClassification variable blocks into the standard resource modules, ensuring that no infrastructure can be deployed without passing the compilation checks.

**Action Item 4.2: Automated Governance Policies**

The LLM is tasked with writing the specific cloud policy definitions in JSON format for AWS Tag Policies or Azure Policy that deny the creation of non-compliant resources. Furthermore, the LLM will provide a Python-based serverless automation script that routinely scans the cloud environment, identifies untagged or orphaned resources, and automatically generates alert payloads to the organization's FinOps messaging channels.

## **Synthesized Recommendations**

The transformation of the baseline agentic platform into an institutional-grade quantitative system requires uncompromising adherence to deterministic architecture principles. By establishing a rigid, event-driven engine modeled on industry standards, the platform securely isolates the probabilistic nature of language models behind impenetrable risk and execution firewalls.

The integration of high-performance internal data representations, leveraging Apache Arrow and Polars, ensures the processing bandwidth necessary for tick-level microstructure analysis without succumbing to memory bloat. The adoption of a plugin architecture and strict MCP tool exposure empowers agents to iterate on trading hypotheses without altering the underlying engine logic. Finally, by embedding project-scoped tagging natively into the infrastructure as code, the system guarantees the strict financial governance required to scale complex quantitative research sustainably. This blueprint provides the exact architectural specifications and operational context necessary for the downstream language model to synthesize, expand, and execute the final, production-ready codebase.

#### **Works cited**

1. The Top Online Trading Platform Trends for 2025 \- Rapyd, accessed April 28, 2026, [https://www.rapyd.net/blog/the-top-online-trading-platform-trends-for-2025/](https://www.rapyd.net/blog/the-top-online-trading-platform-trends-for-2025/)  
2. QuantConnect/Lean: Lean Algorithmic Trading Engine by ... \- GitHub, accessed April 28, 2026, [https://github.com/QuantConnect/Lean](https://github.com/QuantConnect/Lean)  
3. Algorithm Framework \- QuantConnect.com, accessed April 28, 2026, [https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/overview](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/overview)  
4. Documentation \- Algorithm Framework \- Overview \- QuantConnect.com, accessed April 28, 2026, [https://www.quantconnect.com/docs/v1/algorithm-framework/overview](https://www.quantconnect.com/docs/v1/algorithm-framework/overview)  
5. What are the dominant agentic design patterns emerging in financial AI? \- Reddit, accessed April 28, 2026, [https://www.reddit.com/r/algotrading/comments/1rf367u/what\_are\_the\_dominant\_agentic\_design\_patterns/](https://www.reddit.com/r/algotrading/comments/1rf367u/what_are_the_dominant_agentic_design_patterns/)  
6. Algorithm Engine \- QuantConnect.com, accessed April 28, 2026, [https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/algorithm-engine](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/algorithm-engine)  
7. DevPatel-11/event-driven-backtesting-engine \- GitHub, accessed April 28, 2026, [https://github.com/DevPatel-11/event-driven-backtesting-engine](https://github.com/DevPatel-11/event-driven-backtesting-engine)  
8. How I Built an Event-Driven Backtesting Engine in Python | by Timothy Kimutai | Medium, accessed April 28, 2026, [https://timkimutai.medium.com/how-i-built-an-event-driven-backtesting-engine-in-python-25179a80cde0](https://timkimutai.medium.com/how-i-built-an-event-driven-backtesting-engine-in-python-25179a80cde0)  
9. Event-Driven Backtesting with Python \- Part I \- QuantStart, accessed April 28, 2026, [https://www.quantstart.com/articles/Event-Driven-Backtesting-with-Python-Part-I/](https://www.quantstart.com/articles/Event-Driven-Backtesting-with-Python-Part-I/)  
10. A Practical Breakdown of Vector-Based vs. Event-Based Backtesting \- Interactive Brokers, accessed April 28, 2026, [https://www.interactivebrokers.com/campus/ibkr-quant-news/a-practical-breakdown-of-vector-based-vs-event-based-backtesting/](https://www.interactivebrokers.com/campus/ibkr-quant-news/a-practical-breakdown-of-vector-based-vs-event-based-backtesting/)  
11. What Does the Ultimate High-Performance Architecture Look Like? | Harrington Starr, accessed April 28, 2026, [https://www.harringtonstarr.com/resources/podcast/what-does-the-ultimate-high-performance-architecture-look-like-/](https://www.harringtonstarr.com/resources/podcast/what-does-the-ultimate-high-performance-architecture-look-like-/)  
12. A Modular Architecture for Systematic Quantitative Trading Systems | by HIYA CHATTERJEE, accessed April 28, 2026, [https://hiya31.medium.com/a-modular-architecture-for-systematic-quantitative-trading-systems-2a8d46463570](https://hiya31.medium.com/a-modular-architecture-for-systematic-quantitative-trading-systems-2a8d46463570)  
13. Python Libraries for Quantitative Trading | QuantStart, accessed April 28, 2026, [https://www.quantstart.com/articles/python-libraries-for-quantitative-trading/](https://www.quantstart.com/articles/python-libraries-for-quantitative-trading/)  
14. The Ultimate Python Quantitative Trading Ecosystem (2025 Guide) | by Mahmoud Ali, accessed April 28, 2026, [https://medium.com/@mahmoud.abdou2002/the-ultimate-python-quantitative-trading-ecosystem-2025-guide-074c480bce2e](https://medium.com/@mahmoud.abdou2002/the-ultimate-python-quantitative-trading-ecosystem-2025-guide-074c480bce2e)  
15. Python Data Processing 2026: Deep Dive into Pandas, Polars, and DuckDB, accessed April 28, 2026, [https://dev.to/dataformathub/python-data-processing-2026-deep-dive-into-pandas-polars-and-duckdb-2c1](https://dev.to/dataformathub/python-data-processing-2026-deep-dive-into-pandas-polars-and-duckdb-2c1)  
16. Introduction to Polars \- Advancing Analytics, accessed April 28, 2026, [https://www.advancinganalytics.co.uk/blog/2024/1/3/introduction-to-polars](https://www.advancinganalytics.co.uk/blog/2024/1/3/introduction-to-polars)  
17. PyArrow vs Polars (vs DuckDB) for Data Pipelines. \- Confessions of a Data Guy, accessed April 28, 2026, [https://www.confessionsofadataguy.com/pyarrow-vs-polars-vs-duckdb-for-data-pipelines/](https://www.confessionsofadataguy.com/pyarrow-vs-polars-vs-duckdb-for-data-pipelines/)  
18. Polars — DataFrames for the new era, accessed April 28, 2026, [https://pola.rs/](https://pola.rs/)  
19. Top 10 Questions About OHLCV & Tick Data \- CoinAPI.io Blog, accessed April 28, 2026, [https://www.coinapi.io/blog/top-10-questions-about-ohlcv-and-tick-data](https://www.coinapi.io/blog/top-10-questions-about-ohlcv-and-tick-data)  
20. OHLCV Data Explained: Real-Time Updates, WebSocket Behavior & Trading Applications, accessed April 28, 2026, [https://www.coinapi.io/blog/ohlcv-data-explained-real-time-updates-websocket-behavior-and-trading-applications](https://www.coinapi.io/blog/ohlcv-data-explained-real-time-updates-websocket-behavior-and-trading-applications)  
21. Intraday and High-Frequency Market Data APIs | FMP \- Financial Modeling Prep, accessed April 28, 2026, [https://site.financialmodelingprep.com/education/technicalIndicators/intraday-and-highfrequency-market-data-apis-how-to-access-global-ohlcv-data-and-subminute-price-feeds-for-quant-trading-systems](https://site.financialmodelingprep.com/education/technicalIndicators/intraday-and-highfrequency-market-data-apis-how-to-access-global-ohlcv-data-and-subminute-price-feeds-for-quant-trading-systems)  
22. Understanding OHLCV Tick Data Basics & Value as a Data Structure \- CryptoDataDownload, accessed April 28, 2026, [https://www.cryptodatadownload.com/blog/posts/understanding-tick-data-basics-why-important/](https://www.cryptodatadownload.com/blog/posts/understanding-tick-data-basics-why-important/)  
23. Efficient structures for storing tick data : r/quant \- Reddit, accessed April 28, 2026, [https://www.reddit.com/r/quant/comments/1jgxz1j/efficient\_structures\_for\_storing\_tick\_data/](https://www.reddit.com/r/quant/comments/1jgxz1j/efficient_structures_for_storing_tick_data/)  
24. LOBFrame: Python Toolkit for LOB Forecasting \- Emergent Mind, accessed April 28, 2026, [https://www.emergentmind.com/topics/lobframe](https://www.emergentmind.com/topics/lobframe)  
25. Algorithmic Trading : USE Tick Data to OHLC Candlesticks with Python \- Medium, accessed April 28, 2026, [https://medium.com/@kchanchal78/converting-tick-data-to-ohlc-candlesticks-with-python-a064610348cc](https://medium.com/@kchanchal78/converting-tick-data-to-ohlc-candlesticks-with-python-a064610348cc)  
26. TimescaleDB Tutorial: Real-Time Market Data to OHLC Candles Pipeline \- TraderMade, accessed April 28, 2026, [https://tradermade.com/tutorials/6-steps-fx-stock-ticks-ohlc-timescaledb](https://tradermade.com/tutorials/6-steps-fx-stock-ticks-ohlc-timescaledb)  
27. Risk Management \- QuantConnect.com, accessed April 28, 2026, [https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/risk-management/key-concepts](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/risk-management/key-concepts)  
28. Historical Tick Data for Backtesting: Powering Performance \- Intrinio, accessed April 28, 2026, [https://intrinio.com/blog/historical-tick-data-for-backtesting-powering-performance](https://intrinio.com/blog/historical-tick-data-for-backtesting-powering-performance)  
29. High Frequency Trading Platforms: Architecture, Speed & Infrastructure Explained (2026), accessed April 28, 2026, [https://www.quantvps.com/blog/high-frequency-trading-platform](https://www.quantvps.com/blog/high-frequency-trading-platform)  
30. (PDF) A Unified Perspective on Optimization in Machine Learning and Neuroscience: From Gradient Descent to Neural Adaptation \- ResearchGate, accessed April 28, 2026, [https://www.researchgate.net/publication/396747206\_A\_Unified\_Perspective\_on\_Optimization\_in\_Machine\_Learning\_and\_Neuroscience\_From\_Gradient\_Descent\_to\_Neural\_Adaptation](https://www.researchgate.net/publication/396747206_A_Unified_Perspective_on_Optimization_in_Machine_Learning_and_Neuroscience_From_Gradient_Descent_to_Neural_Adaptation)  
31. A Unified Perspective on Optimization in Machine Learning and Neuroscience: From Gradient Descent to Neural Adaptation \- arXiv, accessed April 28, 2026, [https://arxiv.org/html/2510.18812v1](https://arxiv.org/html/2510.18812v1)  
32. Design Extensible Data Pipelines | PDF | Computer Programming | Software Engineering \- Scribd, accessed April 28, 2026, [https://www.scribd.com/document/817664428/Open-Closed-Principles-to-Design-Extensible-Classes](https://www.scribd.com/document/817664428/Open-Closed-Principles-to-Design-Extensible-Classes)  
33. Event Driven Architecture in Algo Trading Platform | by Rajandran R (Creator \- OpenAlgo), accessed April 28, 2026, [https://blog.openalgo.in/event-driven-architecture-in-algo-trading-platform-3a2957ff11a6](https://blog.openalgo.in/event-driven-architecture-in-algo-trading-platform-3a2957ff11a6)  
34. How to Accelerate Quantitative Finance with ISO C++ Standard Parallelism, accessed April 28, 2026, [https://developer.nvidia.com/blog/how-to-accelerate-quantitative-finance-with-iso-c-standard-parallelism/](https://developer.nvidia.com/blog/how-to-accelerate-quantitative-finance-with-iso-c-standard-parallelism/)  
35. How to Design Reliable Data Pipelines \- DEV Community, accessed April 28, 2026, [https://dev.to/alexmercedcoder/how-to-design-reliable-data-pipelines-3kk1](https://dev.to/alexmercedcoder/how-to-design-reliable-data-pipelines-3kk1)  
36. Trade in Minutes\! Rationality-Driven Agentic System for Quantitative Financial Trading \- Microsoft Research, accessed April 28, 2026, [https://www.microsoft.com/en-us/research/publication/trade-in-minutes-rationality-driven-agentic-system-for-quantitative-financial-trading/](https://www.microsoft.com/en-us/research/publication/trade-in-minutes-rationality-driven-agentic-system-for-quantitative-financial-trading/)  
37. Agentic AI for Finance: Workflows, Tips, and Case Studies, accessed April 28, 2026, [https://rpc.cfainstitute.org/research/the-automation-ahead-content-series/agentic-ai-for-finance](https://rpc.cfainstitute.org/research/the-automation-ahead-content-series/agentic-ai-for-finance)  
38. Cloud Tagging Best Practices Explained in 2026 \- nOps, accessed April 28, 2026, [https://www.nops.io/blog/cloud-tagging-best-practices/](https://www.nops.io/blog/cloud-tagging-best-practices/)  
39. Cloud Cost Allocation Guide \- The FinOps Foundation, accessed April 28, 2026, [https://www.finops.org/wg/cloud-cost-allocation/](https://www.finops.org/wg/cloud-cost-allocation/)  
40. Best Practices for Tagging AWS Resources, accessed April 28, 2026, [https://docs.aws.amazon.com/whitepapers/latest/tagging-best-practices/tagging-best-practices.html](https://docs.aws.amazon.com/whitepapers/latest/tagging-best-practices/tagging-best-practices.html)  
41. 5 Best Practices for Building a Cloud Tagging Strategy \- Apptio, accessed April 28, 2026, [https://www.apptio.com/blog/cloud-tagging-best-practices/](https://www.apptio.com/blog/cloud-tagging-best-practices/)  
42. Cloud Tagging: Strategies and Best Practices to Optimize Cost \- TierPoint, accessed April 28, 2026, [https://www.tierpoint.com/blog/cloud/cloud-tagging/](https://www.tierpoint.com/blog/cloud/cloud-tagging/)  
43. Define your tagging strategy \- Cloud Adoption Framework \- Microsoft Learn, accessed April 28, 2026, [https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-tagging](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-tagging)  
44. 12 Cloud Tagging Best Practices To Improve Cloud Cost Management \- ProsperOps, accessed April 28, 2026, [https://www.prosperops.com/blog/cloud-tagging-best-practices/](https://www.prosperops.com/blog/cloud-tagging-best-practices/)  
45. How to implement effective tagging strategies for enterprise data \- Glean, accessed April 28, 2026, [https://www.glean.com/perspectives/how-to-implement-effective-tagging-strategies-for-enterprise-data](https://www.glean.com/perspectives/how-to-implement-effective-tagging-strategies-for-enterprise-data)  
46. AWS Tagging Best Practices for FinOps, Cost Allocation, and Governance \- Hyperglance, accessed April 28, 2026, [https://www.hyperglance.com/blog/aws-tagging-strategy-best-practices/](https://www.hyperglance.com/blog/aws-tagging-strategy-best-practices/)  
47. Getting Started \- QuantConnect.com, accessed April 28, 2026, [https://www.quantconnect.com/docs/v2/lean-cli/key-concepts/getting-started](https://www.quantconnect.com/docs/v2/lean-cli/key-concepts/getting-started)  
48. Tagging Cloud Resources: Best Practices and Importance | by Obedfavour \- Medium, accessed April 28, 2026, [https://medium.com/@obedfavour01/tagging-cloud-resources-best-practices-and-importance-bbe3e2a5a940](https://medium.com/@obedfavour01/tagging-cloud-resources-best-practices-and-importance-bbe3e2a5a940)

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADUAAAAWCAYAAABg3tToAAAA2klEQVR4Xu3VPQoCMRAF4GcpIuJPIdh5GbG19QALXsMreAF7b2Fp7QE8hKVohhgWHqOQXbOJMB9M87bJczMuYIxJ4eTmGTF/QQ46VzIuMFWyIi3dHCgbwx/+Qrm4cVAiuXp9yrbwpTaUS9kjZUx+pAGHZMfBr604gH9DUmpIuRx2QZnm4WbE4dsdn58lpe1TjB70YlJoQlknZvCFzvwgEhfLVkhU0PepiVAsayFxhb5PTRRTqu0+BcVcv1T7FGQptocvJd+pNrRCQSd/6WvUV06bWEV8fI0x5qsXzOY+mvzEOSsAAAAASUVORK5CYII=>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABQAAAAWCAYAAADAQbwGAAAA1klEQVR4Xu2SMQpCMQyG/8FJFPEELm7excHVA3gkwcVVXL1AwNHZCzi4CyqIiCam1RheWxfB4X3w89rkb14aCtT8igHr7oOGHesI9Yj2IdawJks05phAPSOf8KygfywV3EA9LZ+w9FlzFqFc8Jtb4Ba+hLy5C82Ti38gnUmHAiFfcAzND30i0mMtzZ6QL1ic39XtCfmC2flNoe/OQkgfKM5vDX2UVrEDWS/e1idxfsX3Zzkh3eEWmmv7BDPzgcgZ6YJV8+uwDhXx1+zs1SXWDOuSLqj5Px4NX0yoODaQcwAAAABJRU5ErkJggg==>

[image3]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAwAAAAVCAYAAAByrA+0AAAAf0lEQVR4XmNgGH6gCYgfAfF/JAzi9yIrwgZgiokCggwQxQfQxHGCaAaIBj90CVzgNANEAw+6BC5AW/fPYYBo0ESXgIK36AJfGXA7hx+I1yALMDJAFGOYAgVXgFgRWcCYAaJhErIgFCwE4n8wTi4DanJ4B+WDMIgNE2+FaRhxAABk5CYAmiyLKgAAAABJRU5ErkJggg==>

[image4]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAmwAAAAvCAYAAABexpbOAAAFbUlEQVR4Xu3dV6hcVRTG8WWJvaJRbJgoYhcLRuxPltgQERVFUVCC2AULKIgIBnwSG+qDoA9iwfKiQqKgoCgiKChijYld7BIssa7Pvbd3n5UzM5m5YzIz+f9gcfbeZ+6Zy70vi13WMQMAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAjJ7ZHos91grjAAAAGMCjob+5x/qh/6nHkhy/V/e6mWntCdsjHmvEweD90N/N4/QwBgAAsFpQ4rRjGPsp9Iu/PDaMg120JWz6vsvDWBsljM+HsVc8ZoQxAACAiTfXY82qr6XMe6u+bO3xhsffHp94zGve7qgtYTvKes+uFd9Y87MHeVxV9QEAACbauh6XWFrevKYav8Vjj6p/tsfS3NYM23qWlkiX/feJdkq0lPxtEMY1S1Y7zdJS5z4eb3rsVd1TcnZI1dczv636AAAAE+spm0qErsjXH/P1S2suOy72eCi3S8Immm0bRP1zm1qaNdNYmeWr98fN8bit6ssfoQ8AADCRvs/XjS0tW8pv+Rr3r2m2rSRq5Xqqx3v1h/rQlui9VbX1HYUStgeqvpCwAQCA1cKD+Xq9Tc1slcToQ5uaRSu0FKnlUyVTt3rs2bzdl5hwbeVxVm5vZs2E7kiP+VVf/gx9AACAiaTlTyVhOkighK3MuMkdHrtW/ZoSto3iYJ/0nbXrPE7I7UUe21X3tFx7WNXX7/x11QcAAGNEszQ/t4Rqh93vcUE19nT+GdFsjsbiqchCCcIPlj6nREEb3rVpvq5RNq506ODMOOi28FgQB4dIhwvqpO8rS39nza5F+t/UdADi2DAGAADGxBNV+1mPu3JbJSUuzO0vPB7P7eIxa5a0aKPN+UoqihM9fq36K9vecWBAWtbcJA5mL8eBIVPhXNHfvm1Pm2xrUwciis9DHwAAjJGSAIiW7fbNbRV5LWUiVM0/loQ4OvTbPOdxX9W/2Job41e2I+LAgFS+oxMlukpM/y8ne+zicZnHOR47NW//K77pQMV2VQ8OAACMqVJcVWUiNGNT+rqWtmp91RvWb6ja51qaVTrf46JqXPS8Haq+Ns3PqvrTpdOWqmsmd1rvGbQVSdh0+vM7Syc+S/RrnTgwZP0+f+04AAAAxtMplpY+28yyqZkxFXO9Mrcv9bg7txfa8jNLStg+tlThv9PyndxuaS9cp2ijZLJ+pn6/XolJr4TtOI93cls1zl6s7gEAAKxyn3lcHQcrZfbt1dzXxnuNldcnqRaZxgrtsdIzC216LyUohkEzdx9VfSWGkTbo61BFiZNCP6oTwO2t+XwAAIBVqsxWtSUxhe7X+910IrI+iajlTtUg07gcaGnPWvGCpdpgbV7zeL1LtLnHUi00UWKmWTrVO+um1wzbB1VbhzE4VQkAAEbCwR5nWErIDrfOhV11PyYwv1iaYbvRUskOLV8q+TvUUvKjgwnaEyZvexxg6R2XvZYuV4R+HyVVepYON2j27OHGJ5bXK2FbZmlmcI7Hk+EeAADAyNMMVpv98nUb656IKZFTpf9us3j90IyeTrLunvu9DhxIr4RNlKz1KlcyiHlxAAAAYJLt7/FSHBxRx3vMte6HLgAAACaOTnBuGQdHHAkbAADAiBtWwnaexxJLb55QGZJjmrcBAAAwqGEkbHqxvAoF6wX0xdKqDQAAgGnolrDN6BBthx+u9bgpt1XEuNTFAwAAwDR1S9j6oeXQnXN7vjVf/QUAAIAB6CXt71pK2HSd2bzdNz3nGUsnZfU6MAAAAIyYRXEAAAAAo0H72W72WOAxO9wDAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgD79A18p1Tc2Q9qYAAAAAElFTkSuQmCC>

[image5]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAwAAAAXCAYAAAA/ZK6/AAAArklEQVR4XmNgGAWDEUwDYgM0MW4glkQTAwMOIP4PxJ5o4r+BeCuaGBi4MEA08CCJwQwByWEAkCkgSWQAMwTkLAwAkpiEJvYEiN+iiYGBEgNEgz6aOLIhh5ElWhkgkjJIYsFQMZAhikBcjiTH8BwqeRrKrwDiWVAxVyC+BcSMUDkwAEmAbFEA4hAgZoWKgxQFADEzlA8GMPeDaKIAzP1EA1DQgfxANADFJoqHBhYAACvcIRSJL6PJAAAAAElFTkSuQmCC>

[image6]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAwAAAAXCAYAAAA/ZK6/AAAAdklEQVR4XmNgGAWDFUgBcQgWLIKsCAQ0gfg/HtyLUMrAYAYVdEUS2wPE/5D4KACkeAKamC9UHANMYsAusZUBuzjDASD+hC7IAFE8BV0QBBqA+C2aWBkQ/0UTQwEgyRggZgTi6UD8EcrGC7SBOACIWdElRgGpAAAduxxe0wEfgAAAAABJRU5ErkJggg==>

[image7]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAoAAAAXCAYAAAAyet74AAAAq0lEQVR4XmNgGAXUBNZAfBeIZaB8KyB+BMRRcBVAwA/Eq4DYFIj/QxVoQeUOAfEeKJthOQNEsQsDRKECTAIIfKFijCCON1RwK1QQGbRCxXiQBUECk5AFgOAfVBwOpKECmkhiIOeAxCYgiTGUQwUFkcQ2A/FfJD4YPGBA+Bjk8GlA/BXKRgEgRXOAmBmIQxjQHA8DoEAGKdRHl0AHsCDAsAYdgBTBsCea3GAAAIckJB5153kwAAAAAElFTkSuQmCC>

[image8]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAwAAAAXCAYAAAA/ZK6/AAAAyUlEQVR4XmNgGHJAHohZ0QXxgdNAzIguiA98RRfABwSBeD66ID4QDcTG6ILYAMiTfUD8F4jXArE4qjQCgBT+AuJFDBCPfoKK7wHiRzBFMMAPxP+B2AzKR3f/PyDOQeKDrT+AxEd3/0MoBgNPBojpPHBpBoa3SGwQAMlPgnFgGpABKMJgIIYBIg+PcRaogA6Ur8kAcRIISEDlDKB8OAApAkkEMUCs1gDiUwyQUONEUocBxID4NwMitIgCyO4nCJDdTxRoZYBE2lACAFvwIoFlmB6BAAAAAElFTkSuQmCC>

[image9]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAXCAYAAABqBU3hAAAA9klEQVR4XmNgGEGgAoh90QXpAQyAOBSIHzIMkANggCgHHAbiR0D8HwmD+CBMKSDKATBgzACxfCG6BAWAJAe4MUAcsBpdAgnkMqCGFDr2QCgFA4IO0GKAaDwPxH5QdjMQz4KyIxFKyQJ4HVDGALEkGMqHRUE5lC8M5e+B8skBOB3AyIAINhhAdwAIfIOKKSKJEQNgZiFjFMCDRQKbA55DxWyQxKgGfjJADAc5BgSwOQDmSFCIUR2wMkAMf88AsQDdAWuhfAkon2YAlBNAjkCOr78MkKKUroAWBRFJwIoB4oCl6BK0BqC8CrIYVv4j1wujYBSMApoAAMYIUMkR5ma3AAAAAElFTkSuQmCC>